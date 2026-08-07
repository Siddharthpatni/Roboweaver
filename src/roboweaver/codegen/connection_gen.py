"""Deterministic robot-connection adapter generation with optional AI review.

The executable source is generated from a validated registry profile and one of
RoboWeaver's real bridge protocols.  A model may annotate that source and report
issues, but it never replaces the deterministic file and never receives the target
host or port: the URI is supplied at runtime through ``ROBOWEAVER_TARGET_URI``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from roboweaver.codegen.ai_codegen import AICodeReviewer, CodeReviewResult
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.hardware.universal_driver import SimulationHardwareBridge, resolve_bridge_class
from roboweaver.nlu.ollama_manager import get_manager
from roboweaver.nlu.openrouter_manager import OpenRouterManager


CONNECTION_PROVIDERS = ("none", "ollama", "openrouter")
CONNECTION_PROTOCOLS = ("ros2", "sim")


@dataclass
class ConnectionCodeResult:
    robot_id: str
    protocol: str
    filename: str
    code: str
    environment: dict[str, str]
    safety_notes: list[str] = field(default_factory=list)
    annotated_code: str | None = None
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    provider: str = "none"
    model: str = ""
    latency_s: float = 0.0
    ai_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_target_uri(protocol: str, uri: str) -> str:
    candidate = uri.strip()
    if not candidate or len(candidate) > 2048:
        raise ValueError("Connection URI must be 1-2048 characters.")
    parsed = urlparse(candidate)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Connection URI must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("Connection URI must not contain a query string or fragment.")
    if not parsed.hostname or len(parsed.hostname) > 253:
        raise ValueError("Connection URI must contain a valid host.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Connection URI contains an invalid port.") from exc
    if protocol == "ros2":
        if parsed.scheme not in {"ros2", "ros2_control", "dds"}:
            raise ValueError("ROS 2 connection URI must use ros2, ros2_control, or dds.")
    else:
        # Reuse the live bridge's parser so generated adapters cannot accept a
        # target that the runtime bridge would reject later.
        probe = SimulationHardwareBridge(ROBOT_REGISTRY[next(iter(ROBOT_REGISTRY))], candidate)
        probe._parse_target()
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Connection URI port must be between 1 and 65535.")
    return candidate


def _source(robot_id: str, protocol: str) -> str:
    return f'''#!/usr/bin/env python3
"""Generated RoboWeaver connection probe.

This opens and verifies a bridge only. It deliberately sends no trajectory.
"""

import os

from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import resolve_bridge_class


ROBOT_ID = {robot_id!r}
PROTOCOL = {protocol!r}


def main() -> int:
    target_uri = os.environ.get("ROBOWEAVER_TARGET_URI", "").strip()
    if not target_uri:
        raise SystemExit("Set ROBOWEAVER_TARGET_URI before running this adapter.")

    spec = get_robot_spec(ROBOT_ID)
    bridge = resolve_bridge_class(PROTOCOL)(spec, target_uri)
    status = bridge.connect()
    try:
        if not status.is_connected:
            print(f"Connection refused: {{status.message}}")
            return 1
        print(f"Connected to {{status.robot_id}} via {{status.protocol}}")
        print(f"Controllers: {{', '.join(status.active_controllers) or 'none reported'}}")
        print("No motion was sent. Compile and verify a RoboIR program before deployment.")
        return 0
    finally:
        bridge.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
'''


def generate_connection_code(
    robot_id: str,
    protocol: str,
    uri: str,
    provider: str = "none",
    ai_review: bool = False,
) -> ConnectionCodeResult:
    """Generate validated source and optionally request an additive model review."""
    if robot_id not in ROBOT_REGISTRY:
        raise ValueError(f"Unknown robot id '{robot_id}'.")
    canonical_protocol = protocol.strip().lower()
    if canonical_protocol not in CONNECTION_PROTOCOLS:
        raise ValueError(f"Protocol must be one of {CONNECTION_PROTOCOLS}.")
    resolve_bridge_class(canonical_protocol)
    validated_uri = _validate_target_uri(canonical_protocol, uri)
    selected_provider = provider.strip().lower()
    if selected_provider not in CONNECTION_PROVIDERS:
        raise ValueError(f"Provider must be one of {CONNECTION_PROVIDERS}.")

    spec = ROBOT_REGISTRY[robot_id]
    code = _source(robot_id, canonical_protocol)
    result = ConnectionCodeResult(
        robot_id=robot_id,
        protocol=canonical_protocol,
        filename=f"connect_{robot_id}.py",
        code=code,
        environment={"ROBOWEAVER_TARGET_URI": validated_uri},
        safety_notes=[
            "The generated adapter verifies connectivity and sends no robot motion.",
            "A reachable TCP port does not prove the endpoint is the selected robot.",
            "Physical motion still requires compiled RoboIR, simulation validation, and hardware safety controls.",
        ],
        provider=selected_provider if ai_review else "none",
    )
    if not ai_review or selected_provider == "none":
        return result

    manager = get_manager() if selected_provider == "ollama" else OpenRouterManager()
    review: CodeReviewResult = AICodeReviewer(manager).review_connection_python(
        code,
        robot_id=robot_id,
        protocol=canonical_protocol,
        dof=spec.dof,
    )
    result.annotated_code = review.annotated_code
    result.issues = review.issues
    result.suggestions = review.suggestions
    result.model = review.model
    result.latency_s = review.latency_s
    result.ai_error = review.error
    return result
