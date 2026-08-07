"""
Cross-Embodiment Trajectory Retargeter — retargets skills between heterogeneous robot arms.
"""

from __future__ import annotations

from dataclasses import dataclass

from roboweaver.hardware import RobotSpec, NDOFIKSolver, WorkspaceSafetyGuard, forward_kinematics_ndof, get_robot_spec
from roboweaver.types import CompiledSkill, MotionPlan, MotionSegment


@dataclass
class RetargetResult:
    success: bool
    source_robot_id: str
    target_robot_id: str
    retargeted_skill: CompiledSkill
    safety_violations: list[str]


class SkillRetargeter:
    """Retargets compiled skill trajectories across different robot arm hardware."""

    def retarget(self, skill: CompiledSkill, target_robot: str | RobotSpec) -> RetargetResult:
        """Retarget skill trajectories to a new target robot embodiment."""
        source_spec = get_robot_spec(skill.motion_plan.robot_model)

        if isinstance(target_robot, str):
            target_spec = get_robot_spec(target_robot)
        else:
            target_spec = target_robot

        solver = NDOFIKSolver(target_spec)
        guard = WorkspaceSafetyGuard(target_spec)

        violations = []
        new_trajectories: dict[str, MotionSegment] = {}
        new_ik_results = {}

        # Retarget motion plan trajectories
        for desc, seg in skill.motion_plan.trajectories.items():
            retargeted_wps = []
            # Sample subset of waypoints to ensure fast retargeting
            wps_to_retarget = seg.waypoints[::5] if len(seg.waypoints) > 20 else seg.waypoints

            for wp in wps_to_retarget:
                # Compute source robot end-effector Cartesian 3D pose
                ee_tf = forward_kinematics_ndof(source_spec, wp)
                target_pos = ee_tf.pos

                # Check workspace safety bounds for target robot
                check = guard.validate_pose(target_pos)
                if not check.is_safe:
                    violations.extend(check.violations)

                # Solve IK for target robot kinematic chain
                ok, q_sol, residual, iters = solver.solve(target_pos, max_iter=200, tol=0.005)
                if not ok and residual > 0.05:
                    violations.append(f"IK solve residual too high ({residual:.3f}m) for {target_spec.id} at {target_pos}")

                retargeted_wps.append(q_sol)

            new_trajectories[desc] = MotionSegment(
                start_pose=retargeted_wps[0] if retargeted_wps else [0.0] * target_spec.dof,
                end_pose=retargeted_wps[-1] if retargeted_wps else [0.0] * target_spec.dof,
                waypoints=retargeted_wps,
                duration=seg.duration,
            )

        new_plan = MotionPlan(
            trajectories=new_trajectories,
            ik_results=new_ik_results,
            robot_model=target_spec.id,
        )

        retargeted_skill = CompiledSkill(
            intent=skill.intent,
            task_graph=skill.task_graph,
            motion_plan=new_plan,
            behavior_tree=skill.behavior_tree,
        )

        return RetargetResult(
            success=len(violations) == 0,
            source_robot_id=source_spec.id,
            target_robot_id=target_spec.id,
            retargeted_skill=retargeted_skill,
            safety_violations=violations,
        )
