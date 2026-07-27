"""
RoboIR — the intermediate representation between Task Understanding and Skill
Compilation. See docs/REDESIGN.md §2 for the full rationale.

Every stage from Skill Compilation onward reads or writes RoboIR — never the raw
parsed intent directly. This is what makes RoboWeaver a compiler with an IR instead
of a chain of functions that happen to run in order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ObjectRole = Literal["source", "destination", "tool", "obstacle"]
PoseSource = Literal["assumed_default", "perception", "user_specified"]


@dataclass
class ObjectRef:
    """A physical object a skill acts on. `pose_source` is never silently omitted —
    an assumed pose must say so, since RoboWeaver has no perception system yet."""

    id: str
    name: str
    object_class: str
    role: ObjectRole
    color: str | None = None
    pose_source: PoseSource = "assumed_default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "object_class": self.object_class,
            "role": self.role,
            "color": self.color,
            "pose_source": self.pose_source,
        }


@dataclass
class RequiredCapabilities:
    """What a skill needs to run, independent of any one robot. Checked against a
    target RobotSpec's declared capabilities by ir/diagnostics.py (the Compiler
    Debugger) before motion planning proceeds."""

    perception: list[str] = field(default_factory=list)
    manipulation: list[str] = field(default_factory=list)
    sensing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"perception": self.perception, "manipulation": self.manipulation, "sensing": self.sensing}


@dataclass
class Constraints:
    payload_kg: float | None = None
    precision_mm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"payload_kg": self.payload_kg, "precision_mm": self.precision_mm}


@dataclass
class ExecutionSpec:
    robot_id: str
    dof: int
    planner: str = "damped_pseudoinverse_ik"
    controller: str = "position"

    def to_dict(self) -> dict[str, Any]:
        return {"robot_id": self.robot_id, "dof": self.dof, "planner": self.planner, "controller": self.controller}


@dataclass
class VerificationSpec:
    collision_check: bool = True
    simulation_required: bool = True
    safety_checks: list[str] = field(default_factory=lambda: ["reach", "floor", "payload", "joint_limits"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "collision_check": self.collision_check,
            "simulation_required": self.simulation_required,
            "safety_checks": self.safety_checks,
        }


@dataclass
class RoboIR:
    """One compiled skill's intermediate representation."""

    skill_id: str
    skill_version: str
    action: str
    raw_instruction: str
    objects: list[ObjectRef]
    constraints: Constraints
    required_capabilities: RequiredCapabilities
    execution: ExecutionSpec
    verification: VerificationSpec
    parser: str = "rule_based_v1"
    ir_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ir_version": self.ir_version,
            "skill": {"id": self.skill_id, "version": self.skill_version},
            "source": {"raw_instruction": self.raw_instruction, "parser": self.parser},
            "intent": {"action": self.action},
            "objects": [o.to_dict() for o in self.objects],
            "constraints": self.constraints.to_dict(),
            "required_capabilities": self.required_capabilities.to_dict(),
            "execution": self.execution.to_dict(),
            "verification": self.verification.to_dict(),
        }
