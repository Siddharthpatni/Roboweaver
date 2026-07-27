"""
Compiler Debugger — checks a RoboIR's required capabilities against a target
RobotSpec's declared capabilities and produces structured, LLVM/rustc-style
diagnostics instead of a silent failure or a wrong skill.

Perception checks are always warnings, never errors: no perception system exists
anywhere in RoboWeaver today, so a skill that needs `perception.pose_estimation`
would fail on every registered robot if perception were treated as blocking. Being
honest about that gap (docs/REDESIGN.md's audit) is the point -- it's a warning that
the target pose is assumed, not measured, not a reason to refuse to compile.

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
                    'Change execution.controller to "position" for a vision-only approach.',
                    "Select a different robot backend that declares force_torque sensing.",
                ],
            )
        )

    for cap in ir.required_capabilities.perception:
        diagnostics.append(
            CompilerDiagnostic(
                code="RW201",
                severity="warning",
                message=f"Skill '{ir.skill_id}' requires perception.{cap}, which RoboWeaver does not implement yet.",
                reason="No perception system is wired into RoboWeaver -- object poses are assumed defaults, not measured.",
                required_capability=f"perception.{cap}",
                fixes=[
                    "Proceed using an assumed default object pose (current behavior).",
                    "Wire a real perception stage before deploying this skill to physical hardware.",
                ],
            )
        )

    return diagnostics
