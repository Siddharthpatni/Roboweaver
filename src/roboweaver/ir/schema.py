"""
RoboIR — the intermediate representation between Task Understanding and Skill
Compilation. See docs/REDESIGN.md §2 for the full rationale.

Every stage from Skill Compilation onward reads or writes RoboIR — never the raw
parsed intent directly. This is what makes RoboWeaver a compiler with an IR instead
of a chain of functions that happen to run in order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping


def _freeze(value: Any) -> Any:
    """Recursively convert mutable containers into read-only IR values."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Return a JSON-serializable projection without exposing mutable IR state."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_thaw(item) for item in value]
    return value

ObjectRole = Literal["source", "destination", "tool", "obstacle"]
PoseSource = Literal["assumed_default", "perception", "user_specified"]


@dataclass(frozen=True)
class ObjectRef:
    """A physical object a skill acts on. `pose_source` is never silently omitted —
    an assumed pose must say so; accepted external observations carry provenance."""

    id: str
    name: str
    object_class: str
    role: ObjectRole
    color: str | None = None
    pose_source: PoseSource = "assumed_default"
    observation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.observation is not None:
            object.__setattr__(self, "observation", _freeze(self.observation))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "object_class": self.object_class,
            "role": self.role,
            "color": self.color,
            "pose_source": self.pose_source,
            "observation": _thaw(self.observation) if self.observation is not None else None,
        }


CapabilitySource = Literal["declared", "unimplemented"]


@dataclass(frozen=True)
class CapabilityClaim:
    """One structured claim about whether the target robot actually has a required
    capability -- formalizes the distinction ir/diagnostics.py's RW102 (blocking,
    a real declared RobotSpec field backs the claim) vs. RW201 (warning, no
    configured observation satisfies a requirement) into a queryable list.
    `confidence`/`verified` are computed from declared robot facts or validated
    observation provenance -- never an arbitrary score."""

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

    perception: tuple[str, ...] = ()
    manipulation: tuple[str, ...] = ()
    sensing: tuple[str, ...] = ()
    claims: tuple[CapabilityClaim, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "perception", tuple(self.perception))
        object.__setattr__(self, "manipulation", tuple(self.manipulation))
        object.__setattr__(self, "sensing", tuple(self.sensing))
        object.__setattr__(self, "claims", tuple(self.claims))

    def to_dict(self) -> dict[str, Any]:
        return {
            "perception": list(self.perception), "manipulation": list(self.manipulation),
            "sensing": list(self.sensing),
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
    # True only when a supplied Scene was checked against every emitted waypoint.
    # Default compiles without scene geometry must remain false.
    collision_check: bool = False
    simulation_required: bool = True
    safety_checks: tuple[str, ...] = ("reach", "floor", "payload", "joint_limits")

    def __post_init__(self) -> None:
        object.__setattr__(self, "safety_checks", tuple(self.safety_checks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "collision_check": self.collision_check,
            "simulation_required": self.simulation_required,
            "safety_checks": list(self.safety_checks),
        }


@dataclass(frozen=True)
class TaskSummary:
    """Compact index over the complete ProgramSpec task data."""

    task_count: int
    task_types: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_types", tuple(self.task_types))

    def to_dict(self) -> dict[str, Any]:
        return {"task_count": self.task_count, "task_types": list(self.task_types)}


@dataclass(frozen=True)
class MotionSummary:
    """Compact index over the complete LoweringSpec trajectory data."""

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
class IRTask:
    """One target-independent task in execution order."""

    type: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "description": self.description, "parameters": _thaw(self.parameters)}


@dataclass(frozen=True)
class IRBehaviorNode:
    """Target-independent behavior-tree node stored recursively in RoboIR."""

    type: str
    name: str
    children: tuple["IRBehaviorNode", ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", tuple(self.children))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class ProgramSpec:
    """Complete target-independent program produced by the compiler front-end."""

    object_name: str
    parameters: Mapping[str, Any]
    confidence: float
    parse_warnings: tuple[str, ...]
    tasks: tuple[IRTask, ...]
    behavior_tree: IRBehaviorNode

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze(self.parameters))
        object.__setattr__(self, "parse_warnings", tuple(self.parse_warnings))
        object.__setattr__(self, "tasks", tuple(self.tasks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_name": self.object_name,
            "parameters": _thaw(self.parameters),
            "confidence": self.confidence,
            "parse_warnings": list(self.parse_warnings),
            "tasks": [task.to_dict() for task in self.tasks],
            "behavior_tree": self.behavior_tree.to_dict(),
        }


@dataclass(frozen=True)
class IRIKSolution:
    """Auditable evidence for one target-specific IK solve."""

    task_description: str
    joint_angles: tuple[float, ...]
    target_position: tuple[float, ...]
    residual_m: float
    iterations: int
    success: bool
    solver: str = "damped_pseudoinverse_ik"

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_angles", tuple(self.joint_angles))
        object.__setattr__(self, "target_position", tuple(self.target_position))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_description": self.task_description,
            "joint_angles": list(self.joint_angles),
            "target_position": list(self.target_position),
            "residual_m": self.residual_m,
            "iterations": self.iterations,
            "success": self.success,
            "solver": self.solver,
        }


@dataclass(frozen=True)
class IRTrajectory:
    """One complete target-specific trajectory segment."""

    task_description: str
    start_pose: tuple[float, ...]
    end_pose: tuple[float, ...]
    waypoints: tuple[tuple[float, ...], ...]
    duration_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_pose", tuple(self.start_pose))
        object.__setattr__(self, "end_pose", tuple(self.end_pose))
        object.__setattr__(
            self, "waypoints", tuple(tuple(waypoint) for waypoint in self.waypoints),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_description": self.task_description,
            "start_pose": list(self.start_pose),
            "end_pose": list(self.end_pose),
            "waypoints": [list(waypoint) for waypoint in self.waypoints],
            "duration_s": self.duration_s,
        }


@dataclass(frozen=True)
class LoweringSpec:
    """Complete result of independently lowering ProgramSpec to one robot."""

    robot_id: str
    joint_names: tuple[str, ...]
    ik_solutions: tuple[IRIKSolution, ...]
    trajectories: tuple[IRTrajectory, ...]
    motion_model: str = "serial_arm"
    scene_digest: str | None = None
    legalization_trace: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_names", tuple(self.joint_names))
        object.__setattr__(self, "ik_solutions", tuple(self.ik_solutions))
        object.__setattr__(self, "trajectories", tuple(self.trajectories))
        object.__setattr__(self, "legalization_trace", tuple(self.legalization_trace))

    def to_dict(self) -> dict[str, Any]:
        return {
            "robot_id": self.robot_id,
            "joint_names": list(self.joint_names),
            "ik_solutions": [solution.to_dict() for solution in self.ik_solutions],
            "trajectories": [trajectory.to_dict() for trajectory in self.trajectories],
            "motion_model": self.motion_model,
            "scene_digest": self.scene_digest,
            "legalization_trace": list(self.legalization_trace),
        }


@dataclass(frozen=True)
class RoboIR:
    """One compiled skill's intermediate representation.

    Frozen, including nested sequence and mapping values -- an SSA-style guarantee
    that a RoboIR, once built by build_ir(), is never mutated in place. A pass that
    wants to change something produces a *new* RoboIR (dataclasses.replace(ir, ...))
    rather than reassigning a field; ir/pass_manager.py's PassManager threads that
    generation-to-generation, so the compile pipeline is a real IR v1 -> v2 -> v3
    chain, not a mutable object edited in place by whichever stage runs last. Reassigning
    a top-level field raises FrozenInstanceError, sequence mutation has no mutable
    method, and parameter mappings reject assignment.
    """

    skill_id: str
    skill_version: str
    action: str
    raw_instruction: str
    objects: tuple[ObjectRef, ...]
    constraints: Constraints
    required_capabilities: RequiredCapabilities
    execution: ExecutionSpec
    verification: VerificationSpec
    parser: str = "rule_based_v1"
    ir_version: str = "0.2.0"
    task_summary: TaskSummary | None = None
    motion_summary: MotionSummary | None = None
    program: ProgramSpec | None = None
    lowering: LoweringSpec | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "objects", tuple(self.objects))

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
            "program": self.program.to_dict() if self.program else None,
            "lowering": self.lowering.to_dict() if self.lowering else None,
        }
