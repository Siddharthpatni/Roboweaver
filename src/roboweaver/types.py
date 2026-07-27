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


@dataclass
class SkillIntent:
    """Parsed user intent — what the robot should do."""
    action: Action
    object_name: str
    parameters: dict[str, float] = field(default_factory=dict)


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
