"""
RoboWeaver Web Dashboard Server — serves API endpoints and interactive web control center.
"""

from __future__ import annotations

import json
import hmac
import ipaddress
import logging
import math
import os
import platform as platform_module
import re
import socketserver
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from roboweaver import __version__ as ROBOWEAVER_VERSION
from roboweaver.compiler import SkillCompiler
from roboweaver.codegen.groot2 import export_groot2_ir
from roboweaver.knowledge.ingest_registry import build_graph_from_registry
from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
from roboweaver.registry.repository import SkillRepository
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY, distinct_robot_specs
from roboweaver.hardware.kinematics_ndof import forward_kinematics_chain_ndof
from roboweaver.fleet.prompt_builder import SystemPromptParser, MultiRobotChoreographer
from roboweaver.simulation.inspire_sim import InspireHandSimulator
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver
from roboweaver.ir import RoboIR, SkillCompilationError
from roboweaver.json_utils import loads_strict
from roboweaver.hardware.discovery import RobotDiscoveryService, MAX_SCAN_HOSTS
from roboweaver.codegen.urdf_gen import generate_urdf
from roboweaver.codegen.connection_gen import generate_connection_code
from roboweaver.nlu.connection_advisor import advisor_status, build_advisor
from roboweaver.hardware.universal_driver import resolve_bridge_class
from roboweaver.upstream import native_mlir_tool_status

logger = logging.getLogger("roboweaver.dashboard")

# Set once, when this process actually starts serving -- read by /api/version
# so the UI reports real process facts (uptime, whether the self-healing
# supervisor is the one that started this instance) instead of a fabricated
# string. Never written to after start_dashboard_server() is called.
_PROCESS_START_TIME: float | None = None
_SELF_HEALING_ACTIVE = False

# Single source of truth for the RoboIR schema version: read off the
# dataclass's own default rather than duplicating the literal here, so this
# can never drift out of sync with ir/schema.py.
_IR_VERSION = RoboIR.__dataclass_fields__["ir_version"].default

# A browser only sends an `Origin` header on a cross-origin request -- a
# same-page navigation or a non-browser client (curl, the CLI) sends none.
# Matching against "any localhost/127.0.0.1 port" (not a fixed :3000) so the
# real frontend still works if its dev server picks a different port, while
# an external site (whose Origin is its own real domain) is rejected before
# any handler runs -- the previous wildcard CORS header didn't stop that
# fetch from firing (CORS only gates whether JS can *read* the response, not
# whether the request is sent), so a malicious page could silently trigger a
# real side effect like /api/connect. This check does stop it.
_ALLOWED_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")

# Generous enough to never cut off a legitimate slow call (the LLM connect
# advisor can take up to 45s) -- this bounds a stalled *socket* read/write
# (a slow-loris-style client, or one that stops reading its response), not
# how long our own request handling is allowed to run.
_SOCKET_TIMEOUT_S = 60

_MAX_INSTRUCTION_LEN = 2000
_MAX_ROBOTS_PARAM = 20
_MAX_JSON_BODY_BYTES = 4096
_MAX_REQUEST_TARGET_BYTES = 8192
_MAX_QUERY_FIELDS = 32
_ROUTE_NOT_HANDLED = object()
_MAX_REQUEST_ID_LEN = 64
_MIN_CONTROL_TOKEN_LEN = 32
_MAX_CONTROL_TOKEN_LEN = 512
_DEFAULT_RATE_LIMIT_PER_MINUTE = 240
_DEFAULT_EXPENSIVE_RATE_LIMIT_PER_MINUTE = 30
_DEFAULT_MAX_CONCURRENT_REQUESTS = 32
_CONTROL_TOKEN_ENV = "ROBOWEAVER_API_TOKEN"
_ALLOWED_ORIGINS_ENV = "ROBOWEAVER_ALLOWED_ORIGINS"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_PUBLIC_PATHS = frozenset({"/", "/index.html", "/health/live", "/health/ready"})
_EXPENSIVE_PATHS = frozenset({
    "/api/benchmark",
    "/api/build",
    "/api/compare",
    "/api/compile",
    "/api/compile-matrix",
    "/api/artifact",
    "/api/connect/advise",
    "/api/connect/codegen",
    "/api/discover",
    "/api/diff",
    "/api/graph/export-obsidian",
    "/api/research/plan",
    "/api/research/benchmark",
})
_EXPENSIVE_PREFIXES = ("/api/ai/",)


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _validate_control_token(token: str, required: bool) -> None:
    if not token:
        if required:
            raise RuntimeError(
                f"Refusing non-loopback bind without {_CONTROL_TOKEN_ENV}. Set a strong token first."
            )
        return
    if token == "replace-with-a-random-token":
        raise RuntimeError(f"{_CONTROL_TOKEN_ENV} is still the documented placeholder.")
    if not _MIN_CONTROL_TOKEN_LEN <= len(token) <= _MAX_CONTROL_TOKEN_LEN:
        raise RuntimeError(
            f"{_CONTROL_TOKEN_ENV} must be {_MIN_CONTROL_TOKEN_LEN}-{_MAX_CONTROL_TOKEN_LEN} characters."
        )
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise RuntimeError(f"{_CONTROL_TOKEN_ENV} must not contain whitespace or control characters.")


class RequestRateLimiter:
    """Small in-process sliding-window limiter keyed by the TCP peer address.

    It is intentionally independent of proxy headers: trusting an unverified
    X-Forwarded-For value would let a caller evade the limit by changing one
    header. A production gateway should apply its own identity-aware limit too.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def _is_allowed_origin(origin: str | None) -> bool:
    if origin is None:
        return False
    configured = {
        item.strip().rstrip("/")
        for item in os.environ.get(_ALLOWED_ORIGINS_ENV, "").split(",")
        if item.strip()
    }
    return bool(_ALLOWED_ORIGIN_RE.match(origin)) or origin.rstrip("/") in configured


def _is_loopback_bind(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    timeout = _SOCKET_TIMEOUT_S
    server_version = "RoboWeaver"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def do_GET(self):
        """Backstop around _route(): every branch in _route() is expected to
        call self._send_json(...)/self.send_error(...) itself, but proven
        live -- a single unguarded int(query_param) threw an uncaught
        ValueError that left the client with no response at all until its own
        timeout, plus a raw traceback dumped to the server log. Any handler
        can have a gap like that (today's or a future one), so every request
        gets a real response no matter what a handler does internally: the
        client either gets the intended answer or a clean 500, never silence.
        """
        if not self._prepare_request():
            return
        if not self._authorize_api_request():
            return
        self._run_handler(self._route)

    def do_POST(self):
        if not self._prepare_request():
            return

        path = urlparse(self.path).path
        post_handlers = {
            "/api/connect": self._connect_robot,
            "/api/connect/codegen": self._generate_connection_adapter,
            "/api/ai/pull": self._pull_ai_model,
            "/api/ai/config": self._configure_ai_model,
            "/api/research/plan": self._plan_research_experiment,
        }
        if path not in post_handlers:
            self._send_json({"error": "method_not_allowed"}, status=405)
            return
        if not self._authorize_api_request():
            return
        content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_json({"error": "content_type_must_be_application_json"}, status=415)
            return

        payload = self._read_json_body()
        if payload is None:
            return
        self._run_handler(lambda: post_handlers[path](payload))

    def do_OPTIONS(self):
        if not self._prepare_request():
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Request-ID")
        self._send_common_headers()
        self.end_headers()

    def _prepare_request(self) -> bool:
        provided_request_id = self.headers.get("X-Request-ID", "")
        self._request_id = (
            provided_request_id
            if _REQUEST_ID_RE.fullmatch(provided_request_id)
            else uuid.uuid4().hex
        )
        self._request_origin = None
        if len(self.path.encode("utf-8", errors="replace")) > _MAX_REQUEST_TARGET_BYTES:
            self._send_json({"error": "request_target_too_long"}, status=414)
            return False
        parsed = urlparse(self.path)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            self._send_json({"error": "invalid_request_target"}, status=400)
            return False
        origin = self.headers.get("Origin")
        if origin is not None and not _is_allowed_origin(origin):
            self._send_json({"error": "origin_not_allowed"}, status=403)
            return False
        self._request_origin = origin
        if parsed.path not in ("/health/live", "/health/ready"):
            peer = self.client_address[0]
            limiter = getattr(self.server, "rate_limiter", None)
            if limiter is not None and not limiter.allow(peer):
                self._send_json({"error": "rate_limit_exceeded"}, status=429, extra_headers={"Retry-After": "60"})
                return False
            is_expensive = parsed.path in _EXPENSIVE_PATHS or parsed.path.startswith(_EXPENSIVE_PREFIXES)
            expensive_limiter = getattr(self.server, "expensive_rate_limiter", None)
            if is_expensive and expensive_limiter is not None and not expensive_limiter.allow(peer):
                self._send_json({"error": "expensive_rate_limit_exceeded"}, status=429, extra_headers={"Retry-After": "60"})
                return False
        return True

    def _run_handler(self, handler) -> None:
        try:
            handler()
        except BrokenPipeError:
            pass  # client already disconnected -- nothing to send or log
        except Exception:
            logger.exception("Unhandled dashboard request error request_id=%s", self._request_id)
            try:
                self._send_json(
                    {"error": "internal_error", "request_id": self._request_id}, status=500
                )
            except Exception:
                pass  # socket is unusable; nothing more can be done

    def _authorize_api_request(self) -> bool:
        path = urlparse(self.path).path
        if path in _PUBLIC_PATHS:
            return True
        expected = getattr(self.server, "control_token", "")
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        scheme, separator, candidate = supplied.partition(" ")
        if not separator or scheme.lower() != "bearer":
            candidate = ""
        if not candidate or not hmac.compare_digest(candidate, expected):
            self._send_json(
                {"error": "unauthorized"},
                status=401,
                extra_headers={"WWW-Authenticate": 'Bearer realm="RoboWeaver API"'},
            )
            return False
        return True

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"error": "invalid_content_length"}, status=400)
            return None
        if content_length <= 0 or content_length > _MAX_JSON_BODY_BYTES:
            self._send_json(
                {"error": f"JSON body must be 1-{_MAX_JSON_BODY_BYTES} bytes."},
                status=413 if content_length > _MAX_JSON_BODY_BYTES else 400,
            )
            return None
        try:
            payload = loads_strict(self.rfile.read(content_length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "invalid_json"}, status=400)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "JSON body must be an object."}, status=400)
            return None
        return payload

    def _route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            query = parse_qs(parsed.query, max_num_fields=_MAX_QUERY_FIELDS)
        except ValueError:
            self._send_json({"error": f"query accepts at most {_MAX_QUERY_FIELDS} fields."}, status=400)
            return

        handlers = (
            self._route_get_01,
            self._route_get_02,
            self._route_get_03,
            self._route_get_04,
            self._route_get_05,
            self._route_get_06,
            self._route_get_07,
            self._route_get_robot_model,
            self._route_get_robot_urdf,
            self._route_get_robot_fk,
            self._route_get_08,
            self._route_get_09,
            self._route_get_10,
            self._route_get_11,
            self._route_get_12,
            self._route_get_13,
            self._route_get_14,
            self._route_get_15,
            self._route_get_16,
            self._route_get_17,
            self._route_get_18,
            self._route_get_19,
            self._route_get_20,
            self._route_get_21,
            self._route_get_22,
            self._route_get_23,
            self._route_get_24,
            self._route_get_25,
            self._route_get_26,
            self._route_get_27,
            self._route_get_28,
            self._route_get_29,
            self._route_get_30,
            self._route_get_31,
            self._route_get_33,
            self._route_get_32,
        )
        for handler in handlers:
            if handler(path, query) is not _ROUTE_NOT_HANDLED:
                return
        self._send_json({"error": "not_found"}, status=404)

    def _route_get_01(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/knowledge" or path == "/api/graph"):
            return _ROUTE_NOT_HANDLED
        # Real ingestion (knowledge/ingest_registry.py) -- robots/packages/
        # skills/edges from the live registries, not the old ~13-node demo graph.
        kg = build_graph_from_registry()
        self._send_json(kg.to_dict())


    def _route_get_02(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/graph/path"):
            return _ROUTE_NOT_HANDLED
        from_id = query.get("from", [""])[0]
        to_id = query.get("to", [""])[0]
        if not from_id or not to_id:
            self._send_json({"error": "both 'from' and 'to' query params are required"}, status=400)
            return
        kg = build_graph_from_registry()
        path_ids = kg.find_path(from_id, to_id, max_hops=6)
        self._send_json({"from": from_id, "to": to_id, "path": path_ids})


    def _route_get_03(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/graph/export-obsidian"):
            return _ROUTE_NOT_HANDLED
        # Same real export the CLI's `roboweaver graph export-obsidian`
        # command produces (knowledge/obsidian_export.py) -- written to a
        # server-side temp directory (never a client-supplied path) and
        # streamed back as a zip, so "download the Obsidian vault" is a
        # real one-click action from the browser instead of a CLI-only
        # capability.
        import io
        import tempfile
        import zipfile

        from roboweaver.knowledge.obsidian_export import export_to_obsidian

        kg = build_graph_from_registry()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = export_to_obsidian(kg, tmpdir)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for md_file in sorted(Path(out_dir).glob("*.md")):
                    zf.write(md_file, arcname=md_file.name)
            body = buf.getvalue()

        self._send_bytes(
            body,
            content_type="application/zip",
            extra_headers={
                "Content-Disposition": 'attachment; filename="roboweaver-knowledge-graph-obsidian.zip"'
            },
        )


    def _route_get_04(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/nexus/packages"):
            return _ROUTE_NOT_HANDLED
        pkgs = RoboticsPackageNexus.get_all_packages()
        self._send_json([
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "compatible_robots": p.compatible_robots,
                "ros2_dependencies": p.ros2_dependencies,
                "default_topics": p.default_topics,
                "default_actions": p.default_actions,
                "version": p.version,
            }
            for p in pkgs
        ])


    def _route_get_05(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/nexus/recommend"):
            return _ROUTE_NOT_HANDLED
        prompt = query.get("prompt", ["Build ShopMate-R retail assistant with Temi, Pepper, and Franka"])[0]
        if self._reject_if_too_long(prompt, "prompt"):
            return
        rec = RoboticsPackageNexus.recommend_stack_for_prompt(prompt)
        self._send_json(rec)


    def _route_get_06(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/skills"):
            return _ROUTE_NOT_HANDLED
        repo = SkillRepository()
        pkgs = repo.list_packages()
        self._send_json([
            {
                "id": p.id,
                "name": p.name,
                "version": p.version,
                "action": p.action,
                "target_object": p.target_object,
                "description": p.description,
            }
            for p in pkgs
        ])


    def _route_get_07(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/robots"):
            return _ROUTE_NOT_HANDLED
        robots = []
        for spec in distinct_robot_specs():
            robots.append({
                "id": spec.id,
                "name": spec.name,
                "manufacturer": spec.manufacturer,
                "dof": spec.dof,
                "payload_capacity_kg": spec.payload_capacity_kg,
                "max_reach_m": spec.max_reach_m,
                "gripper_type": spec.gripper_type,
                "motion_model": spec.motion_model,
                "description": spec.description,
            })
        self._send_json(robots)

    def _route_get_robot_model(self, path: str, query: dict[str, list[str]]):
        if not (path.startswith("/api/robots/") and path.endswith("/model")):
            return _ROUTE_NOT_HANDLED
        # get_robot_spec() silently falls back to Franka Panda for an
        # unknown id (registry_robots.py; other callers rely on that
        # default, so it isn't changed here) -- checked against
        # ROBOT_REGISTRY directly so a typo'd id in the URL doesn't come
        # back as a 200 with the wrong robot's kinematics.
        robot_id = path[len("/api/robots/"):-len("/model")]
        if robot_id not in ROBOT_REGISTRY:
            self._send_json({"error": f"Unknown robot id '{robot_id}'."}, status=404)
            return
        spec = ROBOT_REGISTRY[robot_id]
        self._send_json({
            "id": spec.id,
            "name": spec.name,
            "dof": spec.dof,
            "base_height_m": spec.base_height_m,
            "max_reach_m": spec.max_reach_m,
            "motion_model": spec.motion_model,
            "kinematic_chains": spec.kinematic_chains,
            "collision_radius_m": spec.collision_radius_m,
            "joints": [
                {
                    "name": j.name,
                    "type": j.type,
                    "axis": list(j.axis),
                    "lower_limit": j.lower_limit,
                    "upper_limit": j.upper_limit,
                }
                for j in spec.joints
            ],
            "links": [{"name": l.name, "length": l.length, "mass": l.mass} for l in spec.links],
        })

    def _route_get_robot_urdf(self, path: str, query: dict[str, list[str]]):
        if not (path.startswith("/api/robots/") and path.endswith("/urdf")):
            return _ROUTE_NOT_HANDLED
        # get_robot_spec() silently falls back to Franka Panda for an
        # unknown id (a pre-existing gap in registry_robots.py, not
        # introduced here) -- checked against ROBOT_REGISTRY directly so
        # this endpoint doesn't inherit that and hand back the wrong
        # robot's model with a 200.
        robot_id = path[len("/api/robots/"):-len("/urdf")]
        if robot_id not in ROBOT_REGISTRY:
            self._send_json({"error": f"Unknown robot id '{robot_id}'."}, status=404)
            return
        spec = ROBOT_REGISTRY[robot_id]
        urdf_xml = generate_urdf(spec)
        body = urdf_xml.encode("utf-8")
        self._send_bytes(
            body,
            content_type="application/xml; charset=utf-8",
            extra_headers={"Content-Disposition": f'attachment; filename="{spec.id}.urdf"'},
        )

    def _route_get_robot_fk(self, path: str, query: dict[str, list[str]]):
        if not (path.startswith("/api/robots/") and path.endswith("/fk")):
            return _ROUTE_NOT_HANDLED
        robot_id = path[len("/api/robots/"):-len("/fk")]
        if robot_id not in ROBOT_REGISTRY:
            self._send_json({"error": f"Unknown robot id '{robot_id}'."}, status=404)
            return
        spec = ROBOT_REGISTRY[robot_id]
        q_param = query.get("q", [""])[0]
        if q_param:
            try:
                q = [float(v) for v in q_param.split(",")]
            except ValueError:
                self._send_json(
                    {"error": "q must be a comma-separated list of finite numbers."},
                    status=400,
                )
                return
        else:
            q = [0.0] * spec.dof
        if len(q) != spec.dof or not all(math.isfinite(value) for value in q):
            self._send_json(
                {"error": f"q must contain exactly {spec.dof} finite joint values."},
                status=400,
            )
            return
        positions = forward_kinematics_chain_ndof(spec, q)
        self._send_json({
            "id": spec.id,
            "q": q,
            # Real forward-kinematics chain -- the exact function the compiler's
            # motion planner uses -- not a client-side approximation.
            "positions": [[p.x, p.y, p.z] for p in positions],
        })


    def _route_get_08(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/build"):
            return _ROUTE_NOT_HANDLED
        prompt = query.get(
            "prompt",
            [
                "Franka Panda pick up the red cube, KUKA iiwa tighten the M8 bolt, "
                "ABB weld the steel seam"
            ],
        )[0]
        if self._reject_if_too_long(prompt, "prompt"):
            return

        parsed = SystemPromptParser.parse(prompt)
        if not parsed.tasks:
            self._send_json(
                {
                    "error": "compilation_failed",
                    "warnings": parsed.warnings,
                    "diagnostics": [
                        {
                            "code": "RW101",
                            "severity": "error",
                            "message": "The workcell prompt contains no supported executable task.",
                            "reason": "; ".join(parsed.warnings),
                            "required_capability": None,
                            "fixes": [
                                "Assign each robot an explicit supported action and target."
                            ],
                        }
                    ],
                },
                status=400,
            )
            return
        choreographer = MultiRobotChoreographer(workcell_name=parsed.workcell_name)
        for t in parsed.tasks:
            choreographer.add_robot_task(
                step_id=t["step_id"],
                robot_id=t["robot_id"],
                instruction=t["instruction"],
                depends_on=t["depends_on"],
                handover_target=t["handover_target"],
            )
        try:
            schedule = choreographer.compile_workcell(verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {
                    "error": "compilation_failed",
                    "warnings": parsed.warnings,
                    "diagnostics": [diagnostic.to_dict() for diagnostic in exc.diagnostics],
                },
                status=400,
            )
            return
        tiers = schedule.get_execution_tiers()
        bt_xml = choreographer.generate_composite_behavior_tree()

        res = {
            "prompt": prompt,
            "workcell_name": parsed.workcell_name,
            "robots": sorted({step.robot_id for step in schedule.steps.values()}),
            "warnings": parsed.warnings,
            "tiers": [
                [
                    {
                        "step_id": s.step_id,
                        "robot_id": s.robot_id,
                        "instruction": s.instruction,
                        "depends_on": s.depends_on,
                        "handover_target": s.handover_target,
                        "action": s.compiled_skill.intent.action.value if s.compiled_skill else None,
                    }
                    for s in tier
                ]
                for tier in tiers
            ],
            "behavior_tree_xml": bt_xml,
        }
        self._send_json(res)


    def _route_get_09(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/simulate/gestures"):
            return _ROUTE_NOT_HANDLED
        self._send_json(list(InspireHandRS485Driver.GESTURES.keys()))


    def _route_get_10(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/simulate/objects"):
            return _ROUTE_NOT_HANDLED
        self._send_json([
            {
                "id": key,
                "name": obj.name,
                "diameter_mm": obj.diameter_mm,
                "compatible_gestures": obj.compatible_gestures,
                "min_hold_force_n": obj.min_hold_force_n,
                "max_safe_force_n": obj.max_safe_force_n,
            }
            for key, obj in InspireHandSimulator.OBJECT_CATALOG.items()
        ])


    def _route_get_11(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/simulate"):
            return _ROUTE_NOT_HANDLED
        gesture = query.get("gesture", ["open"])[0]
        object_key = query.get("object", ["medical_vial"])[0]

        if gesture not in InspireHandRS485Driver.GESTURES:
            self._send_json({"error": f"Unknown gesture '{gesture}'"}, status=400)
            return
        if object_key not in InspireHandSimulator.OBJECT_CATALOG:
            self._send_json({"error": f"Unknown object '{object_key}'"}, status=400)
            return

        sim = InspireHandSimulator()
        sim.load_object(object_key)
        sim.driver.set_gesture(gesture)
        for _ in range(5):
            state = sim.step(dt=0.05)

        total_force = round(sum(state.actuator_forces_n), 2)
        res = {
            "gesture": state.gesture_active,
            "object": object_key,
            "is_simulated": sim.driver.simulated,
            "connect_fallback_reason": sim.driver.last_connect_error,
            "actuator_positions": state.actuator_positions,
            "actuator_currents_ma": state.actuator_currents_ma,
            "actuator_forces_n": state.actuator_forces_n,
            "total_force_n": total_force,
            "object_name": sim.current_object.name if sim.current_object else None,
            "object_status": sim.current_object.status if sim.current_object else "NO OBJECT LOADED",
            "stability_score": round(sim.stability_score, 2),
            "slip_risk": sim.current_object.slip_risk if sim.current_object else 0.0,
        }
        self._send_json(res)


    def _route_get_12(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/compile"):
            return _ROUTE_NOT_HANDLED
        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        robot_id = query.get("robot", ["franka_panda"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        if not self._require_robot_id(robot_id):
            return

        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {
                    "error": "compilation_failed",
                    "diagnostics": [d.to_dict() for d in exc.diagnostics],
                },
                status=400,
            )
            return

        bt_xml = export_groot2_ir(result.ir)

        res = {
            "instruction": instruction,
            "robot": robot_id,
            "intent": {
                "action": result.skill.intent.action.value,
                "object_name": result.skill.intent.object_name,
                "parameters": result.skill.intent.parameters,
                "confidence": result.skill.intent.confidence,
            },
            "tasks": [
                {"type": t.type.value, "description": t.description}
                for t in result.skill.task_graph.tasks
            ],
            "behavior_tree_xml": bt_xml,
            "ir": result.ir.to_dict(),
            "diagnostics": [d.to_dict() for d in result.diagnostics],
            "native_mlir": result.native_mlir.to_dict() if result.native_mlir else None,
        }
        # Additive: the real Pass Manager traces (ir/pass_manager.py,
        # optimize/pass_manager.py), opt-in via a query param so the default
        # response shape/size is unchanged for existing callers.
        self._augment_compile_explanation(res, result, robot_id, query)
        self._send_json(res)

    @staticmethod
    def _augment_compile_explanation(res, result, robot_id, query) -> None:
        pipeline = result.pipeline.to_dict() if result.pipeline is not None else None
        skill_pipeline = (
            result.skill_pipeline.to_dict() if result.skill_pipeline is not None else None
        )
        if query.get("explain_passes", ["0"])[0] == "1":
            if pipeline is not None:
                res["pipeline"] = pipeline
            if skill_pipeline is not None:
                res["skill_pipeline"] = skill_pipeline
        if query.get("explain", ["0"])[0] != "1":
            return
        from roboweaver.nlu.skill_explainer import SkillExplainer
        explanation_input = dict(res)
        if pipeline is not None:
            explanation_input["pipeline"] = pipeline
        if skill_pipeline is not None:
            explanation_input["skill_pipeline"] = skill_pipeline
        spec = ROBOT_REGISTRY.get(robot_id)
        spec_dict = ({
            "gripper_type": spec.gripper_type,
            "payload_capacity_kg": spec.payload_capacity_kg,
            "max_reach_m": spec.max_reach_m,
        } if spec else None)
        explanation = SkillExplainer().explain_compilation(explanation_input, spec_dict)
        res.update({
            "explanation": explanation.text,
            "explanation_model": explanation.model,
            "explanation_latency_s": round(explanation.latency_s, 3),
            "explanation_error": explanation.error,
        })


    def _route_get_13(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/compile-matrix"):
            return _ROUTE_NOT_HANDLED
        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        robots_param = query.get("robots", [""])[0]
        robot_ids = [r.strip() for r in robots_param.split(",") if r.strip()] or [
            "franka_panda", "ur5e", "kuka_iiwa", "kinova_gen3", "abb_irb120",
        ]
        if len(robot_ids) > _MAX_ROBOTS_PARAM:
            self._send_json(
                {"error": f"'robots' accepts at most {_MAX_ROBOTS_PARAM} ids."},
                status=400,
            )
            return
        if not self._require_robot_ids(robot_ids):
            return

        try:
            matrix = SkillCompiler.compile_targets(instruction, robot_ids, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {
                    "error": "compilation_failed",
                    "diagnostics": [diagnostic.to_dict() for diagnostic in exc.diagnostics],
                },
                status=400,
            )
            return
        self._send_json({
            "instruction": instruction,
            "source_digest": matrix.source_digest,
            "portable": {
                "action": matrix.portable.intent.action.value,
                "object_name": matrix.portable.intent.object_name,
                "parameters": matrix.portable.intent.parameters,
                "confidence": matrix.portable.intent.confidence,
                "warnings": matrix.portable.intent.parse_warnings,
                "tasks": [
                    {
                        "type": task.type.value,
                        "description": task.description,
                        "parameters": task.params,
                    }
                    for task in matrix.portable.task_graph.tasks
                ],
            },
            "targets": {
                robot_id: {
                    "instruction": instruction,
                    "robot": robot_id,
                    "intent": {
                        "action": matrix.portable.intent.action.value,
                        "object_name": matrix.portable.intent.object_name,
                        "parameters": matrix.portable.intent.parameters,
                        "confidence": matrix.portable.intent.confidence,
                    },
                    "tasks": [
                        {"type": task.type.value, "description": task.description}
                        for task in matrix.portable.task_graph.tasks
                    ],
                    "behavior_tree_xml": export_groot2_ir(result.ir),
                    "ir": result.ir.to_dict(),
                    "diagnostics": [d.to_dict() for d in result.diagnostics],
                    "native_mlir": (
                        result.native_mlir.to_dict() if result.native_mlir else None
                    ),
                    "pipeline": result.pipeline.to_dict() if result.pipeline else None,
                    "skill_pipeline": (
                        result.skill_pipeline.to_dict() if result.skill_pipeline else None
                    ),
                }
                for robot_id, result in matrix.results.items()
            },
            "failures": {
                robot_id: [d.to_dict() for d in diagnostics]
                for robot_id, diagnostics in matrix.failures.items()
            },
        })


    def _route_get_14(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/artifact"):
            return _ROUTE_NOT_HANDLED
        """Compile and return an actual target backend artifact.

        ROS 2 is returned as a reproducible zip containing the complete
        ``ament_python`` package. URScript is returned as executable text and
        is accepted only for a verified Universal Robots target.
        """
        import io
        import tempfile
        import zipfile

        from roboweaver.plugins.backend import BACKEND_REGISTRY

        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        robot_id = query.get("robot", ["franka_panda"])[0]
        backend_name = query.get("backend", ["ros2"])[0].lower()
        if self._reject_if_too_long(instruction, "instruction"):
            return
        if not self._require_robot_id(robot_id):
            return
        if backend_name not in BACKEND_REGISTRY:
            self._send_json(
                {
                    "error": "unknown_backend",
                    "registered_backends": BACKEND_REGISTRY.names(),
                },
                status=400,
            )
            return

        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {
                    "error": "compilation_failed",
                    "diagnostics": [d.to_dict() for d in exc.diagnostics],
                },
                status=400,
            )
            return

        backend = BACKEND_REGISTRY.get(backend_name)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = Path(tmpdir)
                artifact_path = backend.compile(result, output_root)
                if artifact_path.is_dir():
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(
                        buffer, "w", compression=zipfile.ZIP_DEFLATED
                    ) as archive:
                        for source in sorted(
                            path for path in artifact_path.rglob("*") if path.is_file()
                        ):
                            relative = source.relative_to(output_root).as_posix()
                            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_DEFLATED
                            info.external_attr = 0o100644 << 16
                            archive.writestr(info, source.read_bytes())
                    body = buffer.getvalue()
                    filename = f"{artifact_path.name}-{robot_id}.zip"
                    content_type = "application/zip"
                else:
                    body = artifact_path.read_bytes()
                    filename = artifact_path.name
                    content_type = "text/plain; charset=utf-8"
        except ValueError as exc:
            self._send_json(
                {"error": "artifact_generation_failed", "reason": str(exc)},
                status=400,
            )
            return

        self._send_bytes(
            body,
            content_type=content_type,
            extra_headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-RoboWeaver-Backend": backend_name,
                "X-RoboWeaver-Robot": robot_id,
            },
        )


    def _route_get_15(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/diff"):
            return _ROUTE_NOT_HANDLED
        # Real cross-robot RoboIR diff -- mirrors cli/main.py::cmd_diff()'s
        # --robot2 path exactly (same compile calls, same ir/diff.py::diff_ir()).
        # Per that function's own docstring, per-pass diffing (no robot2) shows
        # "no differences" for almost every real compile today, since the three
        # registered RoboIR passes are diagnostics-only -- this endpoint
        # deliberately only exposes the honest, substantive comparison.
        from roboweaver.ir.diff import diff_ir

        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        robot_id = query.get("robot", ["franka_panda"])[0]
        robot2_id = query.get("robot2", [""])[0]
        if not robot2_id:
            self._send_json({"error": "'robot2' query param is required"}, status=400)
            return
        if not self._require_robot_ids([robot_id, robot2_id]):
            return

        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {"error": "compilation_failed", "robot": robot_id,
                 "diagnostics": [d.to_dict() for d in exc.diagnostics]},
                status=400,
            )
            return

        compiler2 = SkillCompiler(target_robot=robot2_id)
        try:
            result2 = compiler2.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {"error": "compilation_failed", "robot": robot2_id,
                 "diagnostics": [d.to_dict() for d in exc.diagnostics]},
                status=400,
            )
            return

        diff = diff_ir(result.ir, result2.ir)
        diff_payload = {
            "instruction": instruction,
            "from_robot": robot_id,
            "to_robot": robot2_id,
            "field_changes": {k: list(v) for k, v in diff.field_changes.items()},
            "objects_added": [o.to_dict() for o in diff.objects_added],
            "objects_removed": [o.to_dict() for o in diff.objects_removed],
            "objects_changed": [
                {"before": old.to_dict(), "after": new.to_dict()}
                for old, new in diff.objects_changed
            ],
        }
        if query.get("explain", ["0"])[0] == "1":
            from roboweaver.nlu.skill_explainer import SkillExplainer
            explanation = SkillExplainer().explain_diff(diff_payload)
            diff_payload["explanation"] = explanation.text
            diff_payload["explanation_model"] = explanation.model
            diff_payload["explanation_latency_s"] = round(explanation.latency_s, 3)
            diff_payload["explanation_error"] = explanation.error
        self._send_json(diff_payload)


    def _route_get_16(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/cost"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.optimize.cost_model import compute_cost

        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        robot_id = query.get("robot", ["franka_panda"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        if not self._require_robot_id(robot_id):
            return
        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {"error": "compilation_failed", "diagnostics": [d.to_dict() for d in exc.diagnostics]},
                status=400,
            )
            return
        cost = compute_cost(result.skill, result.ir, compiler.robot_spec)
        self._send_json({
            "instruction": instruction, "robot": robot_id,
            "estimated_cycle_time_s": cost.estimated_cycle_time_s,
            "payload_margin_kg": cost.payload_margin_kg,
            "total_joint_travel_rad": cost.total_joint_travel_rad,
            "manipulability_margin": cost.manipulability_margin,
            "historical_success_rate": cost.historical_success_rate,
        })


    def _route_get_17(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/compare"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.optimize.cost_model import compare_robots

        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        robots_param = query.get("robots", [""])[0]
        # Omitting 'robots' is a real, distinct request now, not an error --
        # it means "let the knowledge graph suggest candidates" (real
        # SUITABLE_FOR edges for this instruction's real skill category), not
        # "compare nothing." compare_robots(robot_ids=None) does that lookup.
        robot_ids = [r.strip() for r in robots_param.split(",") if r.strip()] or None
        if robot_ids is not None and len(robot_ids) > _MAX_ROBOTS_PARAM:
            self._send_json(
                {"error": f"'robots' accepts at most {_MAX_ROBOTS_PARAM} ids -- each one compiles a full skill."},
                status=400,
            )
            return
        if robot_ids is not None and not self._require_robot_ids(robot_ids):
            return
        comparison = compare_robots(instruction, robot_ids)
        self._send_json({
            "instruction": instruction,
            "candidate_source": comparison.candidate_source,
            "ranked": [
                {
                    "robot": rid, "score": score,
                    "cost": {
                        "estimated_cycle_time_s": cost.estimated_cycle_time_s,
                        "payload_margin_kg": cost.payload_margin_kg,
                        "total_joint_travel_rad": cost.total_joint_travel_rad,
                        "manipulability_margin": cost.manipulability_margin,
                        "historical_success_rate": cost.historical_success_rate,
                    },
                }
                for rid, score, cost in comparison.ranked
            ],
            "pareto_optimal": comparison.pareto_optimal,
            "skipped": comparison.skipped,
        })


    def _route_get_18(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/benchmark"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.benchmark.robobench import run_benchmark

        robots_param = query.get("robots", [""])[0]
        # A small default subset (not every registered robot) keeps a live
        # dashboard-triggered call fast and predictable -- the CLI/roboweaver
        # benchmark command is the place to run the full matrix.
        robot_ids = (
            [r.strip() for r in robots_param.split(",") if r.strip()]
            or ["franka_panda", "ur5e", "kuka_iiwa"]
        )
        if len(robot_ids) > _MAX_ROBOTS_PARAM:
            self._send_json(
                {"error": f"'robots' accepts at most {_MAX_ROBOTS_PARAM} ids -- each compiles every skill category."},
                status=400,
            )
            return
        if not self._require_robot_ids(robot_ids):
            return
        report = run_benchmark(robot_ids=robot_ids)
        self._send_json(report.to_dict())


    def _route_get_19(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/discover"):
            return _ROUTE_NOT_HANDLED
        host = query.get("host", [None])[0]
        subnet = query.get("subnet", [None])[0]
        if host and subnet:
            self._send_json({"error": "Use either 'host' or 'subnet', not both."}, status=400)
            return
        if (host and len(host) > 253) or (subnet and len(subnet) > 64):
            self._send_json({"error": "Discovery target is too long."}, status=400)
            return
        # A LAN sweep needs a shorter per-probe timeout than a localhost
        # scan: 254 hosts x 14 ports at 0.8s each would be unusable.
        scanner = RobotDiscoveryService(timeout=0.3 if subnet else 0.8)
        try:
            if subnet:
                result = scanner.scan_subnet(subnet)
            elif host:
                result = scanner.scan_host(host)
            else:
                result = scanner.scan()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(scanner.to_dict(result))


    def _route_get_20(self, path: str, query: dict[str, list[str]]):
        if not (path in ("/health/live", "/health/ready")):
            return _ROUTE_NOT_HANDLED
        self._send_json({
            "status": "ok",
            "check": "liveness" if path.endswith("live") else "readiness",
            "version": ROBOWEAVER_VERSION,
        })


    def _route_get_21(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/version"):
            return _ROUTE_NOT_HANDLED
        uptime = (
            round(time.monotonic() - _PROCESS_START_TIME, 1)
            if _PROCESS_START_TIME is not None
            else None
        )
        self._send_json({
            "roboweaver_version": ROBOWEAVER_VERSION,
            "ir_version": _IR_VERSION,
            "python_version": sys.version.split()[0],
            "platform": platform_module.system(),
            "self_healing_active": _SELF_HEALING_ACTIVE,
            "uptime_seconds": uptime,
            "registered_robots": len(distinct_robot_specs()),
            "native_mlir": native_mlir_tool_status(),
        })


    def _route_get_22(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/network"):
            return _ROUTE_NOT_HANDLED
        scanner = RobotDiscoveryService()
        ranges = scanner.detect_local_networks()
        self._send_json({
            "ranges": [
                {
                    "cidr": r.cidr,
                    "interface_ip": r.interface_ip,
                    "interface_name": r.interface_name,
                    "netmask_source": r.netmask_source,
                    "host_count": r.host_count,
                }
                for r in ranges
            ],
            "max_scan_hosts": MAX_SCAN_HOSTS,
            "advisor": advisor_status(),
        })


    def _route_get_23(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/connect/advise"):
            return _ROUTE_NOT_HANDLED
        provider = query.get("provider", ["ollama"])[0]
        model = query.get("model", [None])[0]
        # A bare int(...) here previously threw an uncaught ValueError for
        # any non-numeric port -- proven live: it left the request hanging
        # with no response (the client got nothing until its own timeout)
        # and dumped a traceback to the server log. Never let a malformed
        # query param reach an unguarded parse.
        try:
            port = int(query.get("port", ["0"])[0] or 0)
        except ValueError:
            self._send_json({"error": "port must be an integer."}, status=400)
            return
        if not 1 <= port <= 65535:
            self._send_json({"error": "port must be between 1 and 65535."}, status=400)
            return
        endpoint = {
            "host": query.get("host", ["localhost"])[0],
            "port": port,
            "banner": query.get("banner", [""])[0],
            "hostname": query.get("hostname", [""])[0],
            "robot_type_guess": query.get("guess", [""])[0],
            "latency_ms": query.get("latency", ["0"])[0],
        }
        bounded_fields = {
            "provider": provider,
            "model": model or "",
            "host": endpoint["host"],
            "banner": endpoint["banner"],
            "hostname": endpoint["hostname"],
            "robot_type_guess": endpoint["robot_type_guess"],
            "latency_ms": endpoint["latency_ms"],
        }
        if any(not isinstance(value, str) for value in bounded_fields.values()):
            self._send_json({"error": "Connection advice fields must be strings."}, status=400)
            return
        limits = {
            "provider": 32,
            "model": 128,
            "host": 253,
            "banner": 512,
            "hostname": 253,
            "robot_type_guess": 128,
            "latency_ms": 32,
        }
        too_long = [name for name, value in bounded_fields.items() if len(value) > limits[name]]
        if too_long:
            self._send_json({"error": "Connection advice field too long.", "fields": too_long}, status=400)
            return
        if provider not in ("ollama", "openrouter"):
            self._send_json({"error": "provider must be 'ollama' or 'openrouter'."}, status=400)
            return
        advice = build_advisor(provider, model).advise(endpoint)
        self._send_json({
            "robot_id": advice.robot_id,
            "protocol": advice.protocol,
            "uri": advice.uri,
            "reasoning": advice.reasoning,
            "confidence": advice.confidence,
            "provider": advice.provider,
            "model": advice.model,
            "error": advice.error,
        })


    def _route_get_24(self, path: str, query: dict[str, list[str]]):
        if not (path in ("/api/connect", "/api/connect/codegen")):
            return _ROUTE_NOT_HANDLED
        self._send_json(
            {"error": "method_not_allowed", "message": f"Use POST {path} with a JSON body."},
            status=405,
        )

    # ── AI Endpoints (local Ollama unless a remote provider is explicit) ──
    # Every /api/ai/* endpoint is additive: if the provider is unavailable,
    # the response carries a stated error, never a silent fallback.


    def _route_get_25(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/status"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.ollama_manager import get_manager
        self._send_json(get_manager().to_status_dict())


    def _route_get_26(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/models"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.ollama_manager import get_manager
        mgr = get_manager()
        models = mgr.list_models()
        self._send_json({
            "available": mgr.is_available(),
            "models": [
                {
                    "name": m.name,
                    "size_bytes": m.size_bytes,
                    "parameter_size": m.parameter_size,
                    "quantization": m.quantization,
                }
                for m in models
            ],
        })


    def _route_get_27(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/explain"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.skill_explainer import SkillExplainer

        instruction = query.get("instruction", ["Pick up the red cube"])[0]
        robot_id = query.get("robot", ["franka_panda"])[0]
        if self._reject_if_too_long(instruction, "instruction"):
            return
        if not self._require_robot_id(robot_id):
            return

        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            self._send_json(
                {"error": "compilation_failed", "diagnostics": [d.to_dict() for d in exc.diagnostics]},
                status=400,
            )
            return

        compile_result = {
            "instruction": instruction,
            "robot": robot_id,
            "intent": {
                "action": result.skill.intent.action.value,
                "object_name": result.skill.intent.object_name,
                "parameters": result.skill.intent.parameters,
                "confidence": result.skill.intent.confidence,
            },
            "tasks": [
                {"type": t.type.value, "description": t.description}
                for t in result.skill.task_graph.tasks
            ],
            "ir": result.ir.to_dict(),
            "diagnostics": [d.to_dict() for d in result.diagnostics],
        }
        if result.pipeline is not None:
            compile_result["pipeline"] = result.pipeline.to_dict()
        if result.skill_pipeline is not None:
            compile_result["skill_pipeline"] = result.skill_pipeline.to_dict()

        spec = ROBOT_REGISTRY.get(robot_id)
        robot_spec_dict = {
            "gripper_type": spec.gripper_type if spec else "unknown",
            "payload_capacity_kg": spec.payload_capacity_kg if spec else 0,
            "max_reach_m": spec.max_reach_m if spec else 0,
        } if spec else None

        explainer = SkillExplainer()
        explanation = explainer.explain_compilation(compile_result, robot_spec_dict)
        self._send_json({
            "instruction": instruction,
            "robot": robot_id,
            "explanation": explanation.text,
            "model": explanation.model,
            "latency_s": round(explanation.latency_s, 3),
            "error": explanation.error,
        }, status=200 if explanation.text else 503)


    def _route_get_28(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/diagnose"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.runtime.ai_recovery import AIRecoveryAdvisor

        diagnostic_code = query.get("diagnostic", [""])[0].upper()
        diagnostic_failures = {
            "RW201": "PERCEPTION_FAILED",
            "RW301": "PERCEPTION_FAILED",
            "RW302": "GRASP_FAILED",
            "RW303": "TARGET_UNREACHABLE",
            "RW304": "JOINT_LIMIT_VIOLATED",
            "RW305": "COLLISION_DETECTED",
            "RW306": "COLLISION_DETECTED",
            "RW501": "JOINT_LIMIT_VIOLATED",
            "RW502": "IK_TIMEOUT",
            "RW505": "JOINT_LIMIT_VIOLATED",
            "RW506": "TIMEOUT",
            "RW507": "COLLISION_DETECTED",
            "RW601": "TIMEOUT",
            "RW602": "COLLISION_DETECTED",
            "RW603": "TIMEOUT",
            "RW604": "TARGET_UNREACHABLE",
            "RW605": "COLLISION_DETECTED",
        }
        if diagnostic_code and diagnostic_code not in diagnostic_failures:
            self._send_json({"error": f"Unknown diagnostic code '{diagnostic_code}'"}, status=400)
            return
        failure_mode = query.get(
            "failure", [diagnostic_failures.get(diagnostic_code, "GRASP_FAILED")]
        )[0]
        robot_id = query.get("robot", ["franka_panda"])[0]
        action = query.get("action", ["PICK"])[0]
        if not self._require_robot_id(robot_id):
            return

        from roboweaver.runtime.recovery import RecoveryEngine, FailureMode as FM
        try:
            fm = FM(failure_mode)
        except ValueError:
            self._send_json({"error": f"Unknown failure mode '{failure_mode}'"}, status=400)
            return

        engine = RecoveryEngine()
        plan = engine.diagnose(fm)

        spec = ROBOT_REGISTRY.get(robot_id)
        spec_dict = {
            "dof": spec.dof if spec else 7,
            "gripper_type": spec.gripper_type if spec else "unknown",
        }

        advisor = AIRecoveryAdvisor()
        advice = advisor.advise(
            failure_mode=failure_mode,
            rule_based_action=plan.recommended_action.value,
            rule_based_reason=plan.reason,
            robot_id=robot_id,
            robot_spec=spec_dict,
            skill_context={"action": action, "diagnostic_code": diagnostic_code or None},
        )

        self._send_json({
            "failure_mode": failure_mode,
            "diagnostic_code": diagnostic_code or None,
            "robot": robot_id,
            "rule_based_action": advice.rule_based_action,
            "rule_based_reason": advice.rule_based_reason,
            "ai_explanation": advice.ai_explanation,
            "ai_root_cause": advice.ai_root_cause,
            "fix_description": advice.fix_description,
            "confidence": advice.confidence,
            "suggested_parameter_changes": advice.ai_suggested_params,
            "model": advice.model,
            "latency_s": round(advice.latency_s, 3),
            "error": advice.error,
        })


    def _route_get_29(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/compose"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.skill_composer import SkillComposer

        instruction = query.get("instruction", [""])[0]
        if not instruction:
            self._send_json({"error": "'instruction' query param is required"}, status=400)
            return
        if self._reject_if_too_long(instruction, "instruction"):
            return

        composer = SkillComposer()
        composition = composer.compose(instruction)

        self._send_json({
            "original_instruction": composition.original_instruction,
            "steps": [
                {
                    "step_id": s.step_id,
                    "instruction": s.instruction,
                    "action": s.action,
                    "target_object": s.target_object,
                    "suggested_robot": s.suggested_robot,
                    "depends_on": s.depends_on,
                    "reasoning": s.reasoning,
                }
                for s in composition.steps
            ],
            "suggested_robots": composition.suggested_robots,
            "choreography_prompt": composition.choreography_prompt,
            "model": composition.model,
            "latency_s": round(composition.latency_s, 3),
            "error": composition.error,
        }, status=200 if composition.steps else 503)


    def _route_get_30(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/enrich"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.knowledge.ai_enrichment import KnowledgeGraphEnricher

        mode = query.get("mode", ["edges"])[0]
        enricher = KnowledgeGraphEnricher()

        if mode == "describe":
            robot_id = query.get("robot", [""])[0]
            if not robot_id:
                self._send_json({"error": "'robot' param required for describe mode"}, status=400)
                return
            if not self._require_robot_id(robot_id):
                return
            result = enricher.describe_robot(robot_id)
            self._send_json({
                "mode": "describe",
                "descriptions": [
                    {
                        "robot_id": d.robot_id,
                        "summary": d.summary,
                        "strengths": d.strengths,
                        "limitations": d.limitations,
                        "ideal_tasks": d.ideal_tasks,
                    }
                    for d in result.robot_descriptions
                ],
                "model": result.model,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
            })
        elif mode == "summary":
            node_id = query.get("node", [""])[0]
            if not node_id:
                self._send_json({"error": "'node' param required for summary mode"}, status=400)
                return
            graph = build_graph_from_registry()
            result = enricher.summarize_obsidian_node(graph, node_id)
            self._send_json({
                "mode": "summary",
                "summaries": [
                    {"node_id": s.node_id, "summary": s.summary}
                    for s in result.obsidian_summaries
                ],
                "model": result.model,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
            }, status=200 if result.obsidian_summaries else 503)
        elif mode == "pairings":
            result = enricher.suggest_pairings()
            self._send_json({
                "mode": "pairings",
                "pairings": [
                    {
                        "robot_a": p.robot_a,
                        "robot_b": p.robot_b,
                        "reasoning": p.reasoning,
                        "suggested_tasks": p.suggested_tasks,
                    }
                    for p in result.robot_pairings
                ],
                "model": result.model,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
            })
        else:
            graph = build_graph_from_registry()
            existing_edges = [
                (
                    edge.target_id.removeprefix("robot_"),
                    edge.source_id.removeprefix("skill_").upper(),
                )
                for edge in graph.edges
                if edge.relation.value == "SUITABLE_FOR"
                and edge.source_id.startswith("skill_")
                and edge.target_id.startswith("robot_")
            ]
            result = enricher.suggest_edges(existing_edges)
            self._send_json({
                "mode": "edges",
                "suggestions": [
                    {
                        "robot_id": e.robot_id,
                        "skill_category": e.skill_category,
                        "confidence": e.confidence,
                        "reasoning": e.reasoning,
                    }
                    for e in result.edge_suggestions
                ],
                "model": result.model,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
            })


    def _route_get_31(self, path: str, query: dict[str, list[str]]):
        if not (path == "/api/ai/chat"):
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.ollama_manager import get_manager

        message = query.get("message", [""])[0]
        if not message:
            self._send_json({"error": "'message' query param is required"}, status=400)
            return
        if self._reject_if_too_long(message, "message"):
            return

        mgr = get_manager()
        if query.get("stream", ["0"])[0] == "1":
            self._send_ai_chat_stream(mgr, message)
            return
        resp = mgr.generate(
            prompt=message,
            feature="chat",
            system=(
                "You are RoboWeaver AI, a helpful assistant for the RoboWeaver "
                "robotics compiler platform. You help users understand robot skill "
                "compilation, motion planning, RoboIR, behavior trees, and the "
                "RoboWeaver pipeline. Be precise, technical, and concise."
            ),
            temperature=0.4,
        )
        self._send_json({
            "message": message,
            "response": resp.text,
            "model": resp.model,
            "latency_s": round(resp.latency_s, 3),
            "error": resp.error,
        }, status=200 if resp.text else 503)


    def _route_get_32(self, path: str, query: dict[str, list[str]]):
        if not (path == "/" or path == "/index.html"):
            return _ROUTE_NOT_HANDLED
        self._send_json(
            {
                "message": "RoboWeaver API server. The web UI is the Next.js frontend.",
                "frontend": "cd frontend && npm run dev  ->  http://localhost:3000",
                "api_docs": "See docs/REDESIGN.md for the API surface.",
            }
        )


    def _route_get_33(self, path: str, query: dict[str, list[str]]):
        if path == "/api/observability":
            from roboweaver.observability.cache import get_result_cache
            from roboweaver.observability.traces import get_trace_registry

            self._send_json({
                "traces": get_trace_registry().report(),
                "cache": get_result_cache().stats(),
                "implementation": "Sentinel-inspired bounded attempts; original dependency-light implementation.",
            })
            return
        if path == "/api/research/benchmark":
            from roboweaver.research.evaluation import run_research_evaluation

            self._send_json(run_research_evaluation().to_dict())
            return
        if path != "/api/research/status":
            return _ROUTE_NOT_HANDLED
        from roboweaver.nlu.gemini_manager import gemini_status
        from roboweaver.nlu.ollama_manager import get_manager
        from roboweaver.nlu.openrouter_manager import openrouter_status

        ollama = get_manager()
        self._send_json({
            "providers": {
                "ollama": {
                    "configured": True,
                    "available": ollama.is_available(timeout=1.0),
                    "model": ollama.model_for_feature("experiment"),
                    "remote": False,
                },
                "gemini": gemini_status(),
                "openrouter": openrouter_status(),
            },
            "cascade": ["ollama", "gemini", "openrouter"],
            "max_attempts": 3,
            "sandbox": {
                "profile": "research",
                "network": "none",
                "root_filesystem": "read_only",
                "devices": "none",
                "command": "docker compose --profile research run --rm experiment-sandbox",
                "physics_adapter": "mujoco",
                "physics_adapter_scope": "executes only inside the isolated sandbox container, not this API process",
            },
            "boundaries": {
                "model_code_execution": False,
                "physical_hardware": False,
                "cache_safety_revalidation": True,
                "prompt_storage": False,
            },
        })


    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        """Return bounded JSON errors without reflecting parser input or versions."""
        try:
            label = HTTPStatus(code).phrase.lower().replace(" ", "_")
        except ValueError:
            label = "http_error"
        self._send_json({"error": label, "status": code}, status=code)

    def _send_common_headers(self) -> None:
        self.send_header("X-Request-ID", getattr(self, "_request_id", "unknown"))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        origin = getattr(self, "_request_origin", None)
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send_bytes(
        self,
        body: bytes,
        *,
        content_type: str,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._send_common_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(
        self,
        data: Any,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(
            body,
            content_type="application/json; charset=utf-8",
            status=status,
            extra_headers=extra_headers,
        )

    def _reject_if_too_long(self, value: str, field_name: str) -> bool:
        """Every instruction/prompt-shaped query param routes into a real
        compile, so an unbounded one is a cheap way to burn CPU on one
        request -- caught here, before it reaches the compiler, rather than
        relying on the compiler itself to bail out quickly."""
        if len(value) > _MAX_INSTRUCTION_LEN:
            self._send_json(
                {"error": f"'{field_name}' exceeds {_MAX_INSTRUCTION_LEN} characters."}, status=400
            )
            return True
        return False

    def _require_robot_id(self, robot_id: str) -> bool:
        if robot_id in ROBOT_REGISTRY:
            return True
        self._send_json({"error": f"Unknown robot id '{robot_id}'."}, status=400)
        return False

    def _require_robot_ids(self, robot_ids: list[str]) -> bool:
        unknown = sorted({robot_id for robot_id in robot_ids if robot_id not in ROBOT_REGISTRY})
        if not unknown:
            return True
        self._send_json(
            {"error": "Unknown robot ids.", "unknown_robot_ids": unknown},
            status=400,
        )
        return False

    def _connect_robot(self, payload: dict[str, Any]) -> None:
        robot_id = payload.get("robot", "franka_panda")
        protocol = payload.get("protocol", "ros2")
        uri = payload.get("uri", "ros2://localhost")
        if not all(isinstance(value, str) for value in (robot_id, protocol, uri)):
            self._send_json({"error": "robot, protocol, and uri must be strings."}, status=400)
            return
        if not robot_id or len(robot_id) > 128 or not protocol or len(protocol) > 32:
            self._send_json({"error": "Invalid robot or protocol identifier."}, status=400)
            return
        if not uri or len(uri) > 2048:
            self._send_json({"error": "Connection URI must be 1-2048 characters."}, status=400)
            return
        if robot_id not in ROBOT_REGISTRY:
            self._send_json(
                {"error": f"Unknown robot id '{robot_id}'.", "is_connected": False}, status=400
            )
            return
        try:
            spec = ROBOT_REGISTRY[robot_id]
            bridge = resolve_bridge_class(protocol)(spec, uri)
            status = bridge.connect()
            self._send_json({
                "robot_id": status.robot_id,
                "is_connected": status.is_connected,
                "protocol": status.protocol,
                "dof": status.dof,
                "active_controllers": status.active_controllers,
                "latency_ms": status.latency_ms,
                "message": status.message,
            }, status=200 if status.is_connected else 400)
        except Exception:
            logger.exception("Robot connection failed request_id=%s robot_id=%s", self._request_id, robot_id)
            self._send_json(
                {"error": "connection_failed", "is_connected": False, "request_id": self._request_id},
                status=400,
            )

    def _generate_connection_adapter(self, payload: dict[str, Any]) -> None:
        robot_id = payload.get("robot")
        protocol = payload.get("protocol")
        uri = payload.get("uri")
        provider = payload.get("provider", "none")
        ai_review = payload.get("ai_review", False)
        if not all(isinstance(value, str) for value in (robot_id, protocol, uri, provider)):
            self._send_json(
                {"error": "robot, protocol, uri, and provider must be strings."}, status=400
            )
            return
        if not isinstance(ai_review, bool):
            self._send_json({"error": "ai_review must be a boolean."}, status=400)
            return
        if len(robot_id) > 128 or len(protocol) > 32 or len(uri) > 2048 or len(provider) > 32:
            self._send_json({"error": "Connection code request field too long."}, status=400)
            return
        try:
            generated = generate_connection_code(
                robot_id=robot_id,
                protocol=protocol,
                uri=uri,
                provider=provider,
                ai_review=ai_review,
            )
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(generated.to_dict())

    def _pull_ai_model(self, payload: dict[str, Any]) -> None:
        from roboweaver.nlu.ollama_manager import get_manager
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            self._send_json({"error": "'model' must be a non-empty string."}, status=400)
            return
        model = model.strip()
        if len(model) > 128 or any(c.isspace() for c in model):
            self._send_json({"error": "Invalid Ollama model name."}, status=400)
            return
        success, message = get_manager().pull_model(model)
        self._send_json(
            {"success": success, "model": model, "message": message},
            status=200 if success else 503,
        )

    def _configure_ai_model(self, payload: dict[str, Any]) -> None:
        from roboweaver.nlu.ollama_manager import get_manager
        feature = payload.get("feature")
        model = payload.get("model")
        if not isinstance(feature, str) or not isinstance(model, str):
            self._send_json({"error": "'feature' and 'model' must be strings."}, status=400)
            return
        mgr = get_manager()
        pulled = {m.name for m in mgr.list_models()}
        if model not in pulled:
            self._send_json(
                {"error": f"Model '{model}' is not pulled locally."}, status=400,
            )
            return
        try:
            mgr.set_model_for_feature(feature, model)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json({
            "success": True,
            "feature": feature,
            "model": mgr.model_for_feature(feature),
        })

    def _plan_research_experiment(self, payload: dict[str, Any]) -> None:
        from roboweaver.research.experiments import ExperimentPlanner

        objective = payload.get("objective")
        use_ai = payload.get("use_ai", True)
        if not isinstance(objective, str) or not objective.strip():
            self._send_json({"error": "'objective' must be a non-empty string."}, status=400)
            return
        if len(objective) > 1000 or not isinstance(use_ai, bool):
            self._send_json({"error": "objective is limited to 1000 characters and use_ai must be boolean."}, status=400)
            return
        try:
            result = ExperimentPlanner().plan(objective, use_ai=use_ai)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json(result.to_dict())

    def _send_ai_chat_stream(self, manager: Any, message: str) -> None:
        """Proxy Ollama's token stream as newline-delimited JSON."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("X-Accel-Buffering", "no")
        self._send_common_headers()
        self.end_headers()
        system = (
            "You are RoboWeaver AI, a helpful assistant for the RoboWeaver robotics "
            "compiler platform. Help users understand robot skill compilation, motion "
            "planning, RoboIR, behavior trees, and safety. Be precise and concise."
        )
        for chunk in manager.generate_stream(
            prompt=message, feature="chat", system=system, temperature=0.4,
        ):
            payload = {
                "token": chunk.text,
                "done": chunk.done,
                "model": chunk.model,
                "latency_s": round(chunk.latency_s, 3),
                "error": chunk.error,
            }
            self.wfile.write(json.dumps(payload).encode("utf-8") + b"\n")
            self.wfile.flush()

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Log the path only; prompts and other query values may be sensitive."""
        path = urlparse(self.path).path[:512]
        logger.info(
            "client=%s request_id=%s method=%s path=%s status=%s bytes=%s",
            self.client_address[0],
            getattr(self, "_request_id", "unknown"),
            self.command,
            path,
            code,
            size,
        )

    def log_message(self, format: str, *args: Any) -> None:
        """Sanitize parser-level diagnostics that bypass log_request()."""
        message = (format % args).replace("\r", "\\r").replace("\n", "\\n")[:1000]
        logger.warning(
            "client=%s request_id=%s protocol_message=%s",
            self.client_address[0],
            getattr(self, "_request_id", "unknown"),
            message,
        )


class ReusableHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded, not just reusable.

    Plain HTTPServer handles one request at a time on a single thread -- proven
    experimentally: a LAN subnet sweep (~8s) or an LLM advisor call (up to 45s)
    blocked every other endpoint, including /api/robots, for the full duration.
    Any tab, any panel, the whole dashboard froze until that one request
    finished. ThreadingMixIn gives each request its own thread so a slow scan
    or a slow model call no longer stalls the rest of the UI.
    """
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        max_requests = _bounded_env_int(
            "ROBOWEAVER_MAX_CONCURRENT_REQUESTS",
            _DEFAULT_MAX_CONCURRENT_REQUESTS,
            1,
            256,
        )
        general_limit = _bounded_env_int(
            "ROBOWEAVER_RATE_LIMIT_PER_MINUTE",
            _DEFAULT_RATE_LIMIT_PER_MINUTE,
            1,
            100_000,
        )
        expensive_limit = _bounded_env_int(
            "ROBOWEAVER_EXPENSIVE_RATE_LIMIT_PER_MINUTE",
            _DEFAULT_EXPENSIVE_RATE_LIMIT_PER_MINUTE,
            1,
            10_000,
        )
        self.control_token = ""
        self.max_concurrent_requests = max_requests
        self.rate_limiter = RequestRateLimiter(general_limit)
        self.expensive_rate_limiter = RequestRateLimiter(expensive_limit)
        self._request_slots = threading.BoundedSemaphore(max_requests)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        # Block the accept loop once all slots are occupied. The kernel backlog
        # remains bounded too, preventing one slow client from creating an
        # unbounded number of Python threads.
        self._request_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def start_dashboard_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    global _PROCESS_START_TIME
    control_token = os.environ.get(_CONTROL_TOKEN_ENV, "")
    _validate_control_token(control_token, required=not _is_loopback_bind(host))
    server_address = (host, port)
    httpd = ReusableHTTPServer(server_address, DashboardHTTPRequestHandler)
    httpd.control_token = control_token
    # Reset on every call, not just the first: after a self-healing restart
    # this is a fresh server instance, so "uptime" should mean time since
    # *this* instance came up, not the OS process's whole lifetime.
    _PROCESS_START_TIME = time.monotonic()
    print(f"\n\033[1;32m🚀 RoboWeaver API server running at: http://{host}:{port}\033[0m")
    if host not in ("127.0.0.1", "localhost"):
        print(f"   \033[1;33m⚠ Bound to {host} -- reachable from other machines on this network.\033[0m")
    print("   Frontend (Engineering Workbench): cd frontend && npm run dev -> http://localhost:3000")
    print("   Press Ctrl+C to stop server.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        httpd.server_close()


def run_dashboard_supervised(port: int = 8080, host: str = "127.0.0.1", max_backoff_s: float = 30.0) -> None:
    """Self-healing supervisor loop: if the server process dies for any reason
    other than a deliberate Ctrl+C, restart it automatically -- no human has
    to notice it went down and rerun the CLI command.

    The per-request backstop in do_GET() already stops one bad request from
    taking down the process; this is the second line of defense for whatever
    that backstop can't catch -- a bind failure, an OS-level socket error, an
    exception escaping serve_forever()'s own accept loop, an OOM in a request
    thread. start_dashboard_server() returning normally means it caught a
    KeyboardInterrupt, i.e. someone deliberately asked it to stop -- that is
    the only case this loop does NOT restart from. Anything else retries with
    exponential backoff (capped) so a persistent failure (e.g. the port held
    by another process) doesn't spin in a tight crash loop, but the loop never
    gives up on its own.
    """
    global _SELF_HEALING_ACTIVE
    if not _is_loopback_bind(host) and not os.environ.get(_CONTROL_TOKEN_ENV, ""):
        raise RuntimeError(
            f"Refusing non-loopback bind without {_CONTROL_TOKEN_ENV}. Set a strong token first."
        )
    _SELF_HEALING_ACTIVE = True
    backoff_s = 1.0
    attempt = 0
    while True:
        try:
            start_dashboard_server(port=port, host=host)
            return  # only reached via a clean, deliberate KeyboardInterrupt shutdown
        except KeyboardInterrupt:
            # A second Ctrl+C during the backoff sleep below also lands here
            # via the sleep() call raising -- treat it the same way: stop.
            print("\nSupervisor received interrupt -- stopping (not restarting).")
            return
        except Exception as exc:
            attempt += 1
            print(
                f"\033[1;31m✗ Dashboard server crashed (attempt {attempt}):\033[0m {exc!r}"
            )
            print(f"  Restarting automatically in {backoff_s:.0f}s ...")
            try:
                time.sleep(backoff_s)
            except KeyboardInterrupt:
                print("\nSupervisor received interrupt during backoff -- stopping.")
                return
            backoff_s = min(backoff_s * 2, max_backoff_s)
