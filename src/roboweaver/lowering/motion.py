"""Full-conversion target legality and motion-model-specific lowerers."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import replace

from roboweaver.compiler_core import (
    CompilerPhase,
    CompilerPluginManifest,
    CompilerPluginRegistry,
    ConversionError,
    ConversionPattern,
    ConversionTarget,
    Operation,
    apply_full_conversion,
)
from roboweaver.hardware.kinematics_ndof import NDOFIKSolver
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Vec3
from roboweaver.optimize.motion_cache import (
    compute_motion_primitives_for_targets,
    generate_min_jerk_traj,
    min_safe_duration,
)
from roboweaver.types import (
    Action,
    IKSolution,
    MotionPlan,
    MotionSegment,
    SkillIntent,
    Task,
    TaskType,
)


class TargetLoweringError(ValueError):
    """Portable source contains operations this embodiment cannot legalize."""

_ALL_ACTIONS = frozenset(Action)
_ALL_TASKS = frozenset(TaskType)


def _legalize_portable_program(
    motion_model: str,
    legal_actions: frozenset[Action],
    legal_task_types: frozenset[TaskType],
    intent: SkillIntent,
    tasks: list[Task],
) -> tuple[str, ...]:
    """Run a bounded full conversion from portable ops to one target dialect."""

    operations = [Operation(f"portable.action.{intent.action.value}")]
    operations.extend(Operation(f"portable.task.{task.type.value}") for task in tasks)
    action_targets = {
        action: f"target.{motion_model}.action.{action.value}" for action in legal_actions
    }
    task_targets = {
        task_type: f"target.{motion_model}.task.{task_type.value}"
        for task_type in legal_task_types
    }
    target = ConversionTarget(
        legal_operations=frozenset((*action_targets.values(), *task_targets.values())),
    )
    patterns = [
        ConversionPattern(
            f"portable.action.{action.value}",
            lambda operation, target_name=target_name: Operation(target_name, operation.attributes),
            f"Lower{action.value.title()}To{motion_model}",
            benefit=2,
        )
        for action, target_name in action_targets.items()
    ]
    patterns.extend(
        ConversionPattern(
            f"portable.task.{task_type.value}",
            lambda operation, target_name=target_name: Operation(target_name, operation.attributes),
            f"Lower{task_type.value.title()}To{motion_model}",
        )
        for task_type, target_name in task_targets.items()
    )
    try:
        result = apply_full_conversion(operations, target, patterns)
    except ConversionError as exc:
        raise TargetLoweringError(f"{motion_model} cannot legalize the portable program: {exc}") from exc
    return result.trace


class MotionLowerer(ABC):
    """Base class for target-specific lowering plugins."""

    motion_model: str
    legal_actions: frozenset[Action]
    legal_task_types: frozenset[TaskType]

    def __init__(self, spec: RobotSpec):
        self.spec = spec

    def lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        trace = _legalize_portable_program(
            self.motion_model, self.legal_actions, self.legal_task_types, intent, tasks,
        )
        return replace(self._lower(intent, tasks, targets), legalization_trace=trace)

    @abstractmethod
    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        raise NotImplementedError


class SerialArmLowerer(MotionLowerer):
    motion_model = "serial_arm"
    legal_actions = _ALL_ACTIONS
    legal_task_types = _ALL_TASKS

    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        del intent
        move_tasks = [task for task in tasks if task.type is TaskType.MOVE_TO]
        if not move_tasks:
            return MotionPlan({}, {}, self.spec.id, self.motion_model)
        primitives, _ = compute_motion_primitives_for_targets(self.spec, targets)
        ik_results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        for index, task in enumerate(move_tasks):
            solution = primitives.ik_solutions[index]
            solution.solver = "damped_pseudoinverse_ik"
            ik_results[task.description] = solution
            trajectories[task.description] = MotionSegment(
                primitives.start_configs[index],
                solution.joint_angles,
                primitives.trajectory_waypoints[index],
                primitives.trajectory_durations[index],
            )
        return MotionPlan(ik_results, trajectories, self.spec.id, self.motion_model)


class HolonomicBaseLowerer(MotionLowerer):
    motion_model = "holonomic_base"
    legal_actions = frozenset({Action.NAVIGATE, Action.INSPECT})
    legal_task_types = _ALL_TASKS

    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        del intent
        move_tasks = [task for task in tasks if task.type is TaskType.MOVE_TO]
        current = [0.0, 0.0, 0.0]
        results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        for task, target in zip(move_tasks, targets):
            heading = math.atan2(target.y - current[1], target.x - current[0])
            goal = [target.x, target.y, heading]
            duration = min_safe_duration(self.spec, current, goal, default=0.6)
            results[task.description] = IKSolution(
                goal, 0.0, 1, True, [target.x, target.y, target.z], "holonomic_se2",
            )
            trajectories[task.description] = MotionSegment(
                list(current), goal, generate_min_jerk_traj(current, goal), duration,
            )
            current = goal
        return MotionPlan(results, trajectories, self.spec.id, self.motion_model)


class DifferentialDriveLowerer(MotionLowerer):
    motion_model = "differential_drive"
    legal_actions = frozenset({Action.NAVIGATE, Action.INSPECT})
    legal_task_types = _ALL_TASKS

    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        del intent
        radius = self.spec.motion_parameters["wheel_radius_m"]
        track = self.spec.motion_parameters["track_width_m"]
        pose_x = pose_y = pose_theta = 0.0
        wheels = [0.0, 0.0]
        results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        move_tasks = [task for task in tasks if task.type is TaskType.MOVE_TO]
        for task, target in zip(move_tasks, targets):
            dx, dy = target.x - pose_x, target.y - pose_y
            heading = math.atan2(dy, dx) if abs(dx) + abs(dy) > 1e-12 else pose_theta
            turn = _wrap_angle(heading - pose_theta)
            distance = math.hypot(dx, dy)
            left_delta = distance / radius - (turn * track) / (2.0 * radius)
            right_delta = distance / radius + (turn * track) / (2.0 * radius)
            goal = [wheels[0] + left_delta, wheels[1] + right_delta]
            duration = min_safe_duration(self.spec, wheels, goal, default=0.6)
            results[task.description] = IKSolution(
                goal, 0.0, 1, True, [target.x, target.y, target.z], "differential_drive_se2",
            )
            trajectories[task.description] = MotionSegment(
                list(wheels), goal, generate_min_jerk_traj(wheels, goal), duration,
            )
            wheels = goal
            pose_x, pose_y, pose_theta = target.x, target.y, heading
        return MotionPlan(results, trajectories, self.spec.id, self.motion_model)


class BranchedHumanoidLowerer(MotionLowerer):
    motion_model = "branched_humanoid"
    legal_actions = _ALL_ACTIONS
    legal_task_types = _ALL_TASKS

    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        del intent
        chain_name = "right_arm" if "right_arm" in self.spec.kinematic_chains else next(
            iter(self.spec.kinematic_chains)
        )
        indices = self.spec.kinematic_chains[chain_name]
        chain_spec = RobotSpec(
            id=f"{self.spec.id}:{chain_name}",
            name=f"{self.spec.name} {chain_name}",
            manufacturer=self.spec.manufacturer,
            dof=len(indices),
            payload_capacity_kg=self.spec.payload_capacity_kg,
            max_reach_m=sum(self.spec.links[index].length for index in indices),
            base_height_m=0.0,
            joints=[self.spec.joints[index] for index in indices],
            links=[self.spec.links[index] for index in indices],
            gripper_type=self.spec.gripper_type,
            has_force_torque_sensor=self.spec.has_force_torque_sensor,
            motion_model="serial_arm",
            collision_radius_m=self.spec.collision_radius_m,
        )
        solver = NDOFIKSolver(chain_spec)
        full_current = [
            max(j.lower_limit, min(j.upper_limit, 0.0))
            for j in self.spec.joints[: self.spec.dof]
        ]
        branch_current = [full_current[index] for index in indices]
        results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        move_tasks = [task for task in tasks if task.type is TaskType.MOVE_TO]
        for task, target in zip(move_tasks, targets):
            # Target coordinates are expressed in the selected branch frame.  The
            # branch origin height remains explicit in RobotSpec metadata/IR.
            ok, branch_q, residual, iterations = solver.solve(target, seed_q=branch_current)
            full_goal = list(full_current)
            for index, value in zip(indices, branch_q):
                full_goal[index] = value
            duration = min_safe_duration(self.spec, full_current, full_goal, default=0.6)
            results[task.description] = IKSolution(
                full_goal, residual, iterations, ok,
                [target.x, target.y, target.z], f"branch_ik:{chain_name}",
            )
            trajectories[task.description] = MotionSegment(
                list(full_current), full_goal,
                generate_min_jerk_traj(full_current, full_goal), duration,
            )
            full_current, branch_current = full_goal, branch_q
        return MotionPlan(results, trajectories, self.spec.id, self.motion_model)


class MultiFingerHandLowerer(MotionLowerer):
    motion_model = "multi_finger_hand"
    legal_actions = frozenset({Action.PICK, Action.OPEN, Action.PUSH})
    legal_task_types = _ALL_TASKS

    def _lower(self, intent: SkillIntent, tasks: list[Task], targets: list[Vec3]) -> MotionPlan:
        move_tasks = [task for task in tasks if task.type is TaskType.MOVE_TO]
        current = [joint.lower_limit for joint in self.spec.joints[: self.spec.dof]]
        close_ratio = max(0.0, min(1.0, float(intent.parameters.get("grasp_ratio", 0.72))))
        if intent.action is Action.OPEN:
            close_ratio = 0.0
        goal = [
            joint.lower_limit + close_ratio * (joint.upper_limit - joint.lower_limit)
            for joint in self.spec.joints[: self.spec.dof]
        ]
        results: dict[str, IKSolution] = {}
        trajectories: dict[str, MotionSegment] = {}
        for index, task in enumerate(move_tasks):
            # Isolated hands cannot translate in Cartesian space.  Spatial MOVE_TO
            # operations are therefore legalized as explicit posture holds until
            # the grasp/release stage; no serial-chain IK is fabricated.
            segment_goal = goal if index == len(move_tasks) - 1 else list(current)
            duration = min_safe_duration(self.spec, current, segment_goal, default=0.3)
            results[task.description] = IKSolution(
                segment_goal, 0.0, 1, True,
                # No Cartesian pose is claimed: the source task retains its
                # requested target, while this isolated hand lowering controls
                # only finger posture in the hand base frame.
                [0.0, 0.0, 0.0], "multi_finger_posture",
            )
            trajectories[task.description] = MotionSegment(
                list(current), segment_goal,
                generate_min_jerk_traj(current, segment_goal), duration,
            )
            current = segment_goal
        return MotionPlan(results, trajectories, self.spec.id, self.motion_model)


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


_BUILTIN_LOWERERS: dict[str, type[MotionLowerer]] = {
    "serial_arm": SerialArmLowerer,
    "holonomic_base": HolonomicBaseLowerer,
    "differential_drive": DifferentialDriveLowerer,
    "branched_humanoid": BranchedHumanoidLowerer,
    "multi_finger_hand": MultiFingerHandLowerer,
}

MOTION_LOWERER_REGISTRY = CompilerPluginRegistry("roboweaver.motion_lowerers")
for _model, _provider in _BUILTIN_LOWERERS.items():
    MOTION_LOWERER_REGISTRY.register(CompilerPluginManifest(
        name=f"roboweaver.{_model}",
        version="1",
        phase=CompilerPhase.TRANSFORMATION,
        capability=_model,
        provider=_provider,
        priority=0,
    ))
MOTION_LOWERER_REGISTRY.discover()


def get_motion_lowerer(spec: RobotSpec) -> MotionLowerer:
    """Resolve a target lowering plugin by the RobotSpec's declared motion model."""
    try:
        manifest = MOTION_LOWERER_REGISTRY.resolve(
            CompilerPhase.TRANSFORMATION, spec.motion_model,
        )
        lowerer_type = manifest.provider
    except LookupError as exc:  # validate() normally catches this at the boundary.
        raise TargetLoweringError(f"no lowerer registered for {spec.motion_model!r}") from exc
    return lowerer_type(spec)
