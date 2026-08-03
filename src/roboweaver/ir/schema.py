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


@dataclass(frozen=True)
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


CapabilitySource = Literal["declared", "unimplemented"]


@dataclass(frozen=True)
class CapabilityClaim:
    """One structured claim about whether the target robot actually has a required
    capability -- formalizes the distinction ir/diagnostics.py's RW102 (blocking,
    a real declared RobotSpec field backs the claim) vs. RW201 (warning, no
    perception system exists so the claim can never be verified) already drew
    ad hoc into a queryable list. `confidence`/`verified` are computed from real
    RobotSpec fields or the honest absence of a perception system -- never an
    arbitrary number."""

    name: str
    confidence: float
    verified: bool
    source: CapabilitySource

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "confidence": self.confidence,
            "verified": self.verified, "source": self.source,
        }


@dataclass(frozen=True)
class RequiredCapabilities:
    """What a skill needs to run, independent of any one robot. Checked against a
    target RobotSpec's declared capabilities by ir/diagnostics.py (the Compiler
    Debugger) before motion planning proceeds."""

    perception: list[str] = field(default_factory=list)
    manipulation: list[str] = field(default_factory=list)
    sensing: list[str] = field(default_factory=list)
    claims: list[CapabilityClaim] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "perception": self.perception, "manipulation": self.manipulation, "sensing": self.sensing,
            "claims": [c.to_dict() for c in self.claims],
        }


@dataclass(frozen=True)
class Constraints:
    payload_kg: float | None = None
    precision_mm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"payload_kg": self.payload_kg, "precision_mm": self.precision_mm}


@dataclass(frozen=True)
class ExecutionSpec:
    robot_id: str
    dof: int
    planner: str = "damped_pseudoinverse_ik"
    controller: str = "position"

    def to_dict(self) -> dict[str, Any]:
        return {"robot_id": self.robot_id, "dof": self.dof, "planner": self.planner, "controller": self.controller}


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class TaskSummary:
    """A real summary of a CompiledSkill's task_graph -- Stage 1 toward RoboIR
    absorbing task/motion data (docs/COMPILER_ROADMAP.md v2 vision, item 1). The
    full task list/behavior tree still live on CompiledSkill; this is a queryable
    summary, not a duplicate of the raw data."""

    task_count: int
    task_types: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"task_count": self.task_count, "task_types": self.task_types}


@dataclass(frozen=True)
class MotionSummary:
    """A real summary of a CompiledSkill's motion_plan. Same Stage-1 rationale as
    TaskSummary -- raw waypoints stay on CompiledSkill."""

    segment_count: int
    total_waypoints: int
    estimated_cycle_time_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_count": self.segment_count,
            "total_waypoints": self.total_waypoints,
            "estimated_cycle_time_s": self.estimated_cycle_time_s,
        }


@dataclass(frozen=True)
class RoboIR:
    """One compiled skill's intermediate representation.

    Frozen (and so are every one of its nested dataclasses: ObjectRef, Constraints,
    RequiredCapabilities, ExecutionSpec, VerificationSpec) -- an SSA-style guarantee
    that a RoboIR, once built by build_ir(), is never mutated in place. A pass that
    wants to change something produces a *new* RoboIR (dataclasses.replace(ir, ...))
    rather than reassigning a field; ir/pass_manager.py's PassManager threads that
    generation-to-generation, so the compile pipeline is a real IR v1 -> v2 -> v3
    chain, not a mutable object edited in place by whichever stage runs last. Reassigning
    a top-level field (e.g. `ir.action = "X"`) now raises FrozenInstanceError. Note this
    is shallow: `objects` is still a `list[ObjectRef]`, so the list's *contents* could in
    principle be mutated in place (`ir.objects.append(...)`) even though the field
    itself can't be reassigned -- every pass in this codebase already treats it as
    read-only, but this is a real limit of stdlib `frozen=True`, not deep immutability.
    """

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
    task_summary: TaskSummary | None = None
    motion_summary: MotionSummary | None = None

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
            "task_summary": self.task_summary.to_dict() if self.task_summary else None,
            "motion_summary": self.motion_summary.to_dict() if self.motion_summary else None,
        }
