"""Runtime compatibility adapters whose only input is complete RoboIR."""

from __future__ import annotations

from roboweaver.ir.schema import IRBehaviorNode, RoboIR
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    IKResult,
    MotionPlan,
    SkillIntent,
    Task,
    TaskGraph,
    TaskType,
    TrajectorySegment,
)


def _behavior(node: IRBehaviorNode) -> BTNode:
    return BTNode(node.type, node.name, [_behavior(child) for child in node.children])


def compiled_skill_from_ir(ir: RoboIR) -> CompiledSkill:
    """Materialize the legacy runtime view exclusively from verified RoboIR.

    This adapter exists while SkillRuntime's public API still accepts CompiledSkill.
    It never reads source text, reparses intent, consults templates, or uses a stale
    CompiledSkill retained by CompilationResult.
    """
    if ir.program is None or ir.lowering is None:
        raise ValueError("Runtime execution requires complete RoboIR program and lowering data")

    intent = SkillIntent(
        action=Action(ir.action),
        object_name=ir.program.object_name,
        parameters=dict(ir.program.parameters),
        confidence=ir.program.confidence,
        parse_warnings=list(ir.program.parse_warnings),
    )
    task_graph = TaskGraph([
        Task(TaskType(task.type), task.description, dict(task.parameters))
        for task in ir.program.tasks
    ])
    ik_results = {
        solution.task_description: IKResult(
            joint_angles=list(solution.joint_angles),
            residual=solution.residual_m,
            iterations=solution.iterations,
            success=solution.success,
            target_pos=list(solution.target_position),
            solver=solution.solver,
        )
        for solution in ir.lowering.ik_solutions
    }
    trajectories = {
        trajectory.task_description: TrajectorySegment(
            start_pose=list(trajectory.start_pose),
            end_pose=list(trajectory.end_pose),
            waypoints=[list(waypoint) for waypoint in trajectory.waypoints],
            duration=trajectory.duration_s,
        )
        for trajectory in ir.lowering.trajectories
    }
    return CompiledSkill(
        intent=intent,
        task_graph=task_graph,
        motion_plan=MotionPlan(
            ik_results=ik_results,
            trajectories=trajectories,
            robot_model=ir.lowering.robot_id,
            lowerer=ir.lowering.motion_model,
            collision_checked=ir.verification.collision_check,
            scene_digest=ir.lowering.scene_digest,
        ),
        behavior_tree=_behavior(ir.program.behavior_tree),
    )
