"""
RoboWeaver Web Dashboard Server — serves API endpoints and interactive web control center.
"""

from __future__ import annotations

import json
import platform as platform_module
import re
import socketserver
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from roboweaver import __version__ as ROBOWEAVER_VERSION
from roboweaver.compiler import SkillCompiler
from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.knowledge.ingest_registry import build_graph_from_registry
from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
from roboweaver.registry.repository import SkillRepository
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.hardware.kinematics_ndof import forward_kinematics_chain_ndof
from roboweaver.fleet.prompt_builder import SystemPromptParser, MultiRobotChoreographer
from roboweaver.simulation.inspire_sim import InspireHandSimulator
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver
from roboweaver.ir import RoboIR, SkillCompilationError
from roboweaver.hardware.discovery import RobotDiscoveryService, MAX_SCAN_HOSTS
from roboweaver.codegen.urdf_gen import generate_urdf
from roboweaver.nlu.connection_advisor import advisor_status, build_advisor
from roboweaver.hardware.universal_driver import UniversalRobotDriver

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


def _is_allowed_origin(origin: str | None) -> bool:
    return origin is not None and bool(_ALLOWED_ORIGIN_RE.match(origin))


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    timeout = _SOCKET_TIMEOUT_S

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
        origin = self.headers.get("Origin")
        if origin is not None and not _is_allowed_origin(origin):
            self.send_error(403, "Origin not allowed")
            return
        self._request_origin = origin
        try:
            self._route()
        except BrokenPipeError:
            pass  # client already disconnected -- nothing to send or log
        except Exception as exc:
            try:
                self._send_json(
                    {"error": "internal_error", "message": str(exc)}, status=500
                )
            except Exception:
                pass  # socket is unusable; nothing more can be done

    def _route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/knowledge" or path == "/api/graph":
            # Real ingestion (knowledge/ingest_registry.py) -- robots/packages/
            # skills/edges from the live registries, not the old ~13-node demo graph.
            kg = build_graph_from_registry()
            self._send_json(kg.to_dict())

        elif path == "/api/graph/path":
            from_id = query.get("from", [""])[0]
            to_id = query.get("to", [""])[0]
            if not from_id or not to_id:
                self._send_json({"error": "both 'from' and 'to' query params are required"}, status=400)
                return
            kg = build_graph_from_registry()
            path_ids = kg.find_path(from_id, to_id, max_hops=6)
            self._send_json({"from": from_id, "to": to_id, "path": path_ids})

        elif path == "/api/graph/export-obsidian":
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

            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="roboweaver-knowledge-graph-obsidian.zip"')
            self.send_header("Content-Length", str(len(body)))
            if self._request_origin is not None:
                self.send_header("Access-Control-Allow-Origin", self._request_origin)
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/nexus/packages":
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

        elif path == "/api/nexus/recommend":
            prompt = query.get("prompt", ["Build ShopMate-R retail assistant with Temi, Pepper, and Franka"])[0]
            if self._reject_if_too_long(prompt, "prompt"):
                return
            rec = RoboticsPackageNexus.recommend_stack_for_prompt(prompt)
            self._send_json(rec)

        elif path == "/api/skills":
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

        elif path == "/api/robots":
            seen: set[str] = set()
            robots = []
            for spec in ROBOT_REGISTRY.values():
                if spec.id in seen:
                    continue
                seen.add(spec.id)
                robots.append({
                    "id": spec.id,
                    "name": spec.name,
                    "manufacturer": spec.manufacturer,
                    "dof": spec.dof,
                    "payload_capacity_kg": spec.payload_capacity_kg,
                    "max_reach_m": spec.max_reach_m,
                    "gripper_type": spec.gripper_type,
                    "description": spec.description,
                })
            self._send_json(robots)

        elif path.startswith("/api/robots/") and path.endswith("/model"):
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

        elif path.startswith("/api/robots/") and path.endswith("/urdf"):
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
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Disposition", f'attachment; filename="{spec.id}.urdf"')
            self.send_header("Content-Length", str(len(body)))
            if self._request_origin is not None:
                self.send_header("Access-Control-Allow-Origin", self._request_origin)
            self.end_headers()
            self.wfile.write(body)

        elif path.startswith("/api/robots/") and path.endswith("/fk"):
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
                    self.send_error(400, "q must be a comma-separated list of numbers")
                    return
            else:
                q = [0.0] * spec.dof
            positions = forward_kinematics_chain_ndof(spec, q)
            self._send_json({
                "id": spec.id,
                "q": q,
                # Real forward-kinematics chain -- the exact function the compiler's
                # motion planner uses -- not a client-side approximation.
                "positions": [[p.x, p.y, p.z] for p in positions],
            })

        elif path == "/api/build":
            prompt = query.get(
                "prompt",
                ["Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"],
            )[0]
            if self._reject_if_too_long(prompt, "prompt"):
                return

            parsed = SystemPromptParser.parse(prompt)
            choreographer = MultiRobotChoreographer(workcell_name=parsed.workcell_name)
            for t in parsed.tasks:
                choreographer.add_robot_task(
                    step_id=t["step_id"],
                    robot_id=t["robot_id"],
                    instruction=t["instruction"],
                    depends_on=t["depends_on"],
                    handover_target=t["handover_target"],
                )
            schedule = choreographer.compile_workcell(verbose=False)
            tiers = schedule.get_execution_tiers()
            bt_xml = choreographer.generate_composite_behavior_tree()

            res = {
                "prompt": prompt,
                "workcell_name": parsed.workcell_name,
                "robots": parsed.robots,
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

        elif path == "/api/simulate/gestures":
            self._send_json(list(InspireHandRS485Driver.GESTURES.keys()))

        elif path == "/api/simulate/objects":
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

        elif path == "/api/simulate":
            gesture = query.get("gesture", ["open"])[0]
            object_key = query.get("object", ["medical_vial"])[0]

            if gesture not in InspireHandRS485Driver.GESTURES:
                self.send_error(400, f"Unknown gesture '{gesture}'")
                return
            if object_key not in InspireHandSimulator.OBJECT_CATALOG:
                self.send_error(400, f"Unknown object '{object_key}'")
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

        elif path == "/api/compile":
            instruction = query.get("instruction", ["Pick up the red cube"])[0]
            robot_id = query.get("robot", ["franka_panda"])[0]
            if self._reject_if_too_long(instruction, "instruction"):
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

            bt_xml = export_groot2_xml(result.skill)

            res = {
                "instruction": instruction,
                "robot": robot_id,
                "intent": {
                    "action": result.skill.intent.action.value,
                    "object_name": result.skill.intent.object_name,
                    "parameters": result.skill.intent.parameters,
                },
                "tasks": [
                    {"type": t.type.value, "description": t.description}
                    for t in result.skill.task_graph.tasks
                ],
                "behavior_tree_xml": bt_xml,
                "ir": result.ir.to_dict(),
                "diagnostics": [d.to_dict() for d in result.diagnostics],
            }
            # Additive: the real Pass Manager traces (ir/pass_manager.py,
            # optimize/pass_manager.py), opt-in via a query param so the default
            # response shape/size is unchanged for existing callers.
            if query.get("explain_passes", ["0"])[0] == "1":
                if result.pipeline is not None:
                    res["pipeline"] = result.pipeline.to_dict()
                if result.skill_pipeline is not None:
                    res["skill_pipeline"] = result.skill_pipeline.to_dict()
            self._send_json(res)

        elif path == "/api/cost":
            from roboweaver.optimize.cost_model import compute_cost

            instruction = query.get("instruction", ["Pick up the red cube"])[0]
            robot_id = query.get("robot", ["franka_panda"])[0]
            if self._reject_if_too_long(instruction, "instruction"):
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

        elif path == "/api/compare":
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

        elif path == "/api/benchmark":
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
            report = run_benchmark(robot_ids=robot_ids)
            self._send_json(report.to_dict())

        elif path == "/api/discover":
            host = query.get("host", [None])[0]
            subnet = query.get("subnet", [None])[0]
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

        elif path == "/api/version":
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
                "registered_robots": len(ROBOT_REGISTRY),
            })

        elif path == "/api/network":
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

        elif path == "/api/connect/advise":
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
            endpoint = {
                "host": query.get("host", ["localhost"])[0],
                "port": port,
                "banner": query.get("banner", [""])[0],
                "hostname": query.get("hostname", [""])[0],
                "robot_type_guess": query.get("guess", [""])[0],
                "latency_ms": query.get("latency", ["0"])[0],
            }
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

        elif path == "/api/connect":
            robot_id = query.get("robot", ["franka_panda"])[0]
            protocol = query.get("protocol", ["ros2"])[0]
            uri = query.get("uri", ["ros2://localhost"])[0]
            # Unlike /model and /fk, "robot" here has an explicit, intentional
            # default (franka_panda) -- that's fine. What must not happen is a
            # *typo'd* id silently opening a bridge to Panda's kinematics while
            # the response still gets read as "connected to <typo>".
            if robot_id not in ROBOT_REGISTRY:
                self._send_json(
                    {"error": f"Unknown robot id '{robot_id}'.", "is_connected": False}, status=400
                )
                return
            try:
                spec = ROBOT_REGISTRY[robot_id]
                bridge = UniversalRobotDriver.connect_robot(spec, protocol=protocol, uri=uri)
                status = bridge.connect()
                self._send_json({
                    "robot_id": status.robot_id,
                    "is_connected": status.is_connected,
                    "protocol": status.protocol,
                    "dof": status.dof,
                    "active_controllers": status.active_controllers,
                    "latency_ms": status.latency_ms,
                    "message": status.message,
                })
            except Exception as exc:
                self._send_json({"error": str(exc), "is_connected": False}, status=400)

        elif path == "/" or path == "/index.html":
            self._send_json(
                {
                    "message": "RoboWeaver API server. The web UI is the Next.js frontend.",
                    "frontend": "cd frontend && npm run dev  ->  http://localhost:3000",
                    "api_docs": "See docs/REDESIGN.md for the API surface.",
                }
            )

        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Echoes the real, already-validated request Origin back (do_GET already
        # rejected anything not matching _ALLOWED_ORIGIN_RE) instead of "*" --
        # a non-browser client (no Origin header) needs no CORS header at all.
        origin = getattr(self, "_request_origin", None)
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(body)

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

    def log_message(self, format, *args):
        pass  # Quiet logging


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


def start_dashboard_server(port: int = 8080, host: str = "127.0.0.1") -> None:
    global _PROCESS_START_TIME
    server_address = (host, port)
    httpd = ReusableHTTPServer(server_address, DashboardHTTPRequestHandler)
    # Reset on every call, not just the first: after a self-healing restart
    # this is a fresh server instance, so "uptime" should mean time since
    # *this* instance came up, not the OS process's whole lifetime.
    _PROCESS_START_TIME = time.monotonic()
    print(f"\n\033[1;32m🚀 RoboWeaver API server running at: http://{host}:{port}\033[0m")
    if host not in ("127.0.0.1", "localhost"):
        print(f"   \033[1;33m⚠ Bound to {host} -- reachable from other machines on this network.\033[0m")
    print(f"   Frontend (Engineering Workbench): cd frontend && npm run dev -> http://localhost:3000")
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

