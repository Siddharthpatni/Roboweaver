"""Fail-closed physical hardware acceptance with tamper-evident output."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from roboweaver.hardware.universal_driver import (
    AbstractRobotBridge,
    SimulationHardwareBridge,
)
from roboweaver.ir.schema import RoboIR


class HILAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HILEvidence:
    schema_version: str
    run_id: str
    started_at: str
    completed_at: str
    operator: str
    robot_id: str
    bridge_type: str
    target_uri: str
    ir_sha256: str
    command_sha256: str
    command_acknowledged: bool
    before_joint_state: tuple[float, ...]
    after_joint_state: tuple[float, ...]
    max_tracking_error: float
    safety_before: dict[str, Any]
    safety_after: dict[str, Any]
    passed: bool
    evidence_sha256: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_sha256", None)
        payload["before_joint_state"] = list(self.before_joint_state)
        payload["after_joint_state"] = list(self.after_joint_state)
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_dict()
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    def verify_digest(self) -> bool:
        return self.evidence_sha256 == _digest(self.unsigned_dict())


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class HILRunner:
    """Execute one deliberately small trajectory and verify physical feedback."""

    CONFIRMATION = "I CONFIRM PHYSICAL ROBOT MOTION"

    def __init__(self, bridge: AbstractRobotBridge, *, tracking_tolerance: float = 0.08):
        if isinstance(bridge, SimulationHardwareBridge):
            raise HILAcceptanceError("simulation bridges cannot produce physical HIL evidence")
        self.bridge = bridge
        self.tracking_tolerance = tracking_tolerance

    def run(
        self,
        ir: RoboIR,
        waypoints: list[list[float]],
        *,
        operator: str,
        confirmation: str,
        settle_s: float = 0.25,
    ) -> HILEvidence:
        self._validate_request(waypoints, operator, confirmation)
        safety_before, before = self._read_ready_state("pre-command")

        started = datetime.now(timezone.utc)
        acknowledged = self.bridge.send_trajectory(waypoints, dt=0.05)
        if not acknowledged:
            raise HILAcceptanceError("physical controller did not acknowledge the trajectory")
        time.sleep(max(0.0, min(settle_s, 5.0)))

        safety_after, after = self._read_ready_state("post-command")
        max_error = self._assess_feedback(before, after, waypoints[-1])

        ir_payload = ir.to_dict()
        command_digest = _digest(waypoints)
        run_id = _digest({
            "robot": self.bridge.spec.id,
            "started": started.isoformat(),
            "ir": _digest(ir_payload),
            "command": command_digest,
        })[:20]
        unsigned = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "operator": operator,
            "robot_id": self.bridge.spec.id,
            "bridge_type": type(self.bridge).__name__,
            "target_uri": self.bridge.target_uri,
            "ir_sha256": _digest(ir_payload),
            "command_sha256": command_digest,
            "command_acknowledged": acknowledged,
            "before_joint_state": list(before),
            "after_joint_state": list(after),
            "max_tracking_error": max_error,
            "safety_before": safety_before,
            "safety_after": safety_after,
            "passed": True,
        }
        return HILEvidence(
            **{**unsigned,
               "before_joint_state": before,
               "after_joint_state": after},
            evidence_sha256=_digest(unsigned),
        )

    @staticmethod
    def _require_safe_io(state: dict[str, Any]) -> None:
        required = {"available", "estop_released", "watchdog_ok", "protective_stop_clear"}
        if not required.issubset(state):
            raise HILAcceptanceError("safety state omits required e-stop/watchdog fields")
        if not all(bool(state[key]) for key in required):
            raise HILAcceptanceError(f"physical safety I/O is not ready: {state}")

    def _validate_request(
        self, waypoints: list[list[float]], operator: str, confirmation: str,
    ) -> None:
        if confirmation != self.CONFIRMATION:
            raise HILAcceptanceError("explicit physical-motion confirmation is required")
        if not operator.strip():
            raise HILAcceptanceError("operator identity is required")
        if not getattr(self.bridge, "_connected", False):
            raise HILAcceptanceError("bridge is not connected to live hardware")
        if not waypoints or any(len(item) != self.bridge.spec.dof for item in waypoints):
            raise HILAcceptanceError("every HIL waypoint must exactly match the robot DOF")
        for waypoint in waypoints:
            if not all(math.isfinite(value) for value in waypoint):
                raise HILAcceptanceError("HIL waypoints must contain finite values")
            for value, joint in zip(waypoint, self.bridge.spec.joints):
                if not joint.lower_limit <= value <= joint.upper_limit:
                    raise HILAcceptanceError(f"waypoint exceeds {joint.name} limits")

    def _read_ready_state(self, phase: str) -> tuple[dict[str, Any], tuple[float, ...]]:
        safety = self.bridge.read_safety_state()
        self._require_safe_io(safety)
        joints = tuple(float(value) for value in self.bridge.read_joint_state())
        if len(joints) != self.bridge.spec.dof or not all(math.isfinite(value) for value in joints):
            raise HILAcceptanceError(f"live {phase} joint feedback is malformed")
        return safety, joints

    def _assess_feedback(
        self, before: tuple[float, ...], after: tuple[float, ...], target: list[float],
    ) -> float:
        max_error = max(abs(actual - expected) for actual, expected in zip(after, target))
        changed = max(abs(post - pre) for pre, post in zip(before, after)) > 1e-5
        if not changed:
            raise HILAcceptanceError("joint feedback did not change; refusing to fabricate HIL success")
        if max_error > self.tracking_tolerance:
            raise HILAcceptanceError(
                f"maximum tracking error {max_error:.6f} exceeds tolerance {self.tracking_tolerance:.6f}"
            )
        return max_error
