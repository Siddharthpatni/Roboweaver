"""Core data types for the RoboWeaver skill compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


# ─── Intent ────────────────────────────────────────────────────────────

class Action(Enum):
    """High-level robot actions the compiler understands."""
    PICK = "PICK"
    PLACE = "PLACE"
    TIGHTEN = "TIGHTEN"
    OPEN = "OPEN"
    PUSH = "PUSH"
    OPEN_DOOR = "OPEN_DOOR"
    TOOL_EXCHANGE = "TOOL_EXCHANGE"
    INSPECT = "INSPECT"
    WELD = "WELD"
    PEG_INSERT = "PEG_INSERT"
    POUR = "POUR"
    PACKAGE = "PACKAGE"
    CNC_LOAD = "CNC_LOAD"
    SURGERY_ASSIST = "SURGERY_ASSIST"
    SORT = "SORT"
    CLEAN = "CLEAN"
    PALLETIZE = "PALLETIZE"
    POLISH = "POLISH"
    DISASSEMBLE = "DISASSEMBLE"
    NAVIGATE = "NAVIGATE"


@dataclass
class SkillIntent:
    """Parsed user intent — what the robot should do.

    `confidence` (0.0-1.0) and `parse_warnings` record how sure Stage 1 actually
    was. A keyword parser will always return *some* action, so silently
    defaulting an unrecognised instruction to PICK would hand the rest of the
    pipeline a guess indistinguishable from a confident parse. These two fields
    keep that distinction visible to every downstream consumer.
    """
    action: Action
    object_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    parse_warnings: list[str] = field(default_factory=list)


def supplied_pose_satisfies_perception(intent: SkillIntent) -> bool:
    """Whether one complete user pose replaces the template's locate-object step.

    This is deliberately narrow. Sorting, pouring, insertion, navigation, and
    compound placement still need classification, secondary-object geometry, or
    localization evidence; one x/y/z triple cannot satisfy those contracts.
    """
    return intent.action is Action.PICK and all(
        key in intent.parameters for key in ("x_m", "y_m", "z_m")
    )


# ─── Task Graph ────────────────────────────────────────────────────────

class TaskType(Enum):
    """Atomic task types in the execution graph."""
    PERCEIVE = "PERCEIVE"
    OPEN_GRIPPER = "OPEN_GRIPPER"
    CLOSE_GRIPPER = "CLOSE_GRIPPER"
    MOVE_TO = "MOVE_TO"
    WAIT = "WAIT"
    VERIFY_GRASP = "VERIFY_GRASP"


@dataclass
class Task:
    """A single atomic task in the execution sequence."""
    type: TaskType
    description: str
    params: dict[str, Any] = field(default_factory=dict)


TaskDecomposition = Task


@dataclass
class TaskGraph:
    """Ordered sequence of tasks to execute."""
    tasks: list[Task]


# ─── Motion Planning ──────────────────────────────────────────────────

@dataclass
class IKResult:
    """Result of an inverse kinematics solve."""
    joint_angles: Sequence[float]
    residual: float
    iterations: int
    success: bool = True
    target_pos: Sequence[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    solver: str = "damped_pseudoinverse_ik"


IKSolution = IKResult


@dataclass
class TrajectorySegment:
    """A smooth trajectory between two joint configurations."""
    start_pose: Sequence[float]
    end_pose: Sequence[float]
    waypoints: Sequence[Sequence[float]]   # shape: (n_steps, n_joints)
    duration: float                         # seconds


MotionSegment = TrajectorySegment


@dataclass
class MotionPlan:
    """All motion plans for a compiled skill."""
    ik_results: dict[str, IKResult]              # name → IK solution
    trajectories: dict[str, TrajectorySegment]   # name → trajectory
    robot_model: str = "panda"
    lowerer: str = "serial_arm"
    collision_checked: bool = False
    scene_digest: str | None = None
    legalization_trace: tuple[str, ...] = ()


# ─── Behavior Tree ────────────────────────────────────────────────────

@dataclass
class BTNode:
    """A node in the behavior tree."""
    type: str       # 'Sequence', 'Fallback', 'Action', 'Condition', 'Decorator'
    name: str
    children: list[BTNode] = field(default_factory=list)

    def pretty(self, prefix: str = "", is_last: bool = True) -> str:
        """Render a tree-formatted string."""
        connector = "└─ " if is_last else "├─ "
        line = f"{prefix}{connector}{self.type}: {self.name}\n"
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(self.children):
            line += child.pretty(child_prefix, i == len(self.children) - 1)
        return line


# ─── Compiled Skill & Execution ───────────────────────────────────────

@dataclass
class CompiledSkill:
    """Full output of the compilation pipeline."""
    intent: SkillIntent
    task_graph: TaskGraph
    motion_plan: MotionPlan
    behavior_tree: BTNode


@dataclass(frozen=True)
class PortableSkill:
    """Target-independent compiler front-end output.

    A PortableSkill contains only semantics: parsed intent, ordered tasks and
    behavior. It deliberately has no RobotSpec, IK solution, joint waypoint or
    controller selection. ``SkillCompiler.lower()`` binds it to one concrete
    embodiment and performs motion planning and safety verification there.
    """

    intent: SkillIntent
    task_graph: TaskGraph
    behavior_tree: BTNode
    raw_instruction: str


@dataclass
class ExecutionResult:
    """Outcome of executing a skill in simulation."""
    success: bool
    initial_object_height: float
    final_object_height: float
    height_gained: float
    cycle_time: float
    joint_limits_respected: bool
    frames: list[str] = field(default_factory=list)
    telemetry_frame_count: int = 0
    recovery_events: list[str] = field(default_factory=list)
    validation_level: str = "unvalidated"
    validated_claims: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    failure_reason: str | None = None


def estimate_cycle_time(skill: CompiledSkill) -> float:
    """Real, computed total cycle time: summed trajectory durations plus WAIT task
    durations -- nothing estimated beyond what the compiler itself already produced.
    One shared implementation: ir/builder.py's RoboIR motion summary,
    optimize/passes.py::CompiledSkillVerificationPass, and optimize/cost_model.py
    all call this instead of recomputing it independently."""
    total = sum(seg.duration for seg in skill.motion_plan.trajectories.values())
    total += sum(
        float(t.params.get("duration", 0.0))
        for t in skill.task_graph.tasks
        if t.type is TaskType.WAIT
    )
    return total
