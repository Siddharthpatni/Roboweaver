"""
Compiler Debugger — checks a RoboIR's required capabilities against a target
RobotSpec's declared capabilities and produces structured, LLVM/rustc-style
diagnostics instead of a silent failure or a wrong skill.

Unsatisfied perception checks are warnings for source that still uses an assumed pose.
A configured observation provider validates timestamp, frame, confidence, calibration,
and finite coordinates before compilation; a valid measured pose removes only the
capability requirement it actually satisfies.

Sensing checks (e.g. force/torque) are blocking: RobotSpec.has_force_torque_sensor is
real, declared per-robot data, so a mismatch here is a genuine, checkable compile error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from roboweaver.ir.schema import RoboIR
from roboweaver.hardware.robot_spec import RobotSpec

Severity = Literal["error", "warning"]


@dataclass
class CompilerDiagnostic:
    code: str
    severity: Severity
    message: str
    reason: str
    required_capability: str | None
    fixes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "reason": self.reason,
            "required_capability": self.required_capability,
            "fixes": self.fixes,
        }


class SkillCompilationError(Exception):
    """Raised when a RoboIR requires a capability the target robot backend cannot
    satisfy. Carries the blocking diagnostics that caused the refusal."""

    def __init__(self, diagnostics: list[CompilerDiagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(d.message for d in diagnostics))


def check_required_capabilities(ir: RoboIR, robot_spec: RobotSpec) -> list[CompilerDiagnostic]:
    diagnostics: list[CompilerDiagnostic] = []

    if "force_torque" in ir.required_capabilities.sensing and not robot_spec.has_force_torque_sensor:
        diagnostics.append(
            CompilerDiagnostic(
                code="RW102",
                severity="error",
                message=f"Cannot compile skill '{ir.skill_id}' for backend '{robot_spec.id}'.",
                reason=(
                    f"RoboIR requires sensing.force_torque (controller={ir.execution.controller!r}), "
                    f"but {robot_spec.name} does not declare a force/torque sensor."
                ),
                required_capability="sensing.force_torque",
                fixes=[
                    "Attach and register a force/torque sensor on this robot's RobotSpec.",
                    "Use a different task/controller only if it truthfully removes the force-control requirement.",
                    "Select a different robot backend that declares force_torque sensing.",
                ],
            )
        )

    for cap in ir.required_capabilities.perception:
        assumed_pose = any(obj.pose_source == "assumed_default" for obj in ir.objects)
        diagnostics.append(
            CompilerDiagnostic(
                code="RW201",
                severity="warning",
                message=f"Skill '{ir.skill_id}' still requires perception.{cap}.",
                reason=(
                    "No validated external observation was supplied -- object poses are assumed defaults, not measured."
                    if assumed_pose
                    else "The supplied pose does not satisfy this action's full perception contract."
                ),
                required_capability=f"perception.{cap}",
                fixes=[
                    "Proceed only in a controlled scene with the disclosed pose provenance.",
                    "Configure a validated observation provider before physical deployment.",
                ],
            )
        )

    return diagnostics
