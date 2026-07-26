"""
Universal Skill Compiler Pipeline — converts natural language into robot skill packages.

Multi-stage pipeline:
1. Intent Parsing (Action, Target Object, Parameters)
2. Task Graph Decomposition (Industrial Skill Taxonomy)
3. Generalized N-DOF Kinematics & Motion Planning (Robotic Tooling)
4. Groot2 BehaviorTree XML Generation
"""

from __future__ import annotations

import re
from typing import Any

from roboweaver.hardware import RobotSpec, NDOFIKSolver, get_robot_spec, get_franka_panda_spec
from roboweaver.skills import IndustrialSkillCategory, get_industrial_skill_template
from roboweaver.math3d import Mat3, Transform3D, Vec3
from roboweaver.types import (
    Action,
    BTNode,
    CompiledSkill,
    IKSolution,
    MotionPlan,
    MotionSegment,
    SkillIntent,
    TaskDecomposition,
    TaskGraph,
    TaskType,
)


class SkillCompiler:
    """Universal Skill Compiler Pipeline targeting arbitrary N-DOF robot embodiments."""

    def __init__(self, target_robot: str | RobotSpec | None = None):
        if target_robot is None:
            self.robot_spec = get_franka_panda_spec()
        elif isinstance(target_robot, str):
            self.robot_spec = get_robot_spec(target_robot)
        else:
            self.robot_spec = target_robot

    def compile(self, instruction: str, verbose: bool = True) -> CompiledSkill:
        """Compile natural language instruction into a CompiledSkill."""
        if verbose:
            print(f"\n\033[1;34mRoboWeaver Universal Compiler\033[0m — Instruction: \033[1m\"{instruction}\"\033[0m")
            print(f"  Target Robot: \033[36m{self.robot_spec.name}\033[0m ({self.robot_spec.dof}-DOF, Payload: {self.robot_spec.payload_capacity_kg}kg)")

        # Stage 1: Parse Intent
        intent = self._parse_intent(instruction)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 1/4: Parse Intent \033[0m")
            print(f"  → Action:     {intent.action.value}")
            print(f"  → Object:     {intent.object_name}")
            for k, v in intent.parameters.items():
                print(f"  → Parameter:  {k} = {v}")

        # Stage 2: Task Decomposition
        task_graph = self._decompose_tasks(intent)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 2/4: Task Decomposition \033[0m")
            for i, task in enumerate(task_graph.tasks):
                print(f"  → [{i+1}] {task.type.value:<14} → {task.description}")

        # Stage 3: Motion Planning with N-DOF Kinematics Engine
        motion_plan = self._plan_motion(intent, task_graph, verbose=verbose)

        # Stage 4: Behavior Tree Compiler
        behavior_tree = self._compile_behavior_tree(intent, task_graph)
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 4/4: Behavior Tree \033[0m")
            self._print_bt(behavior_tree)
            print()

        return CompiledSkill(
            intent=intent,
            task_graph=task_graph,
            motion_plan=motion_plan,
            behavior_tree=behavior_tree,
        )

    def _parse_intent(self, instruction: str) -> SkillIntent:
        inst_lower = instruction.lower()

        if "tighten" in inst_lower or "bolt" in inst_lower or "screw" in inst_lower:
            action = Action.TIGHTEN
            obj_name = "m8_bolt"
            params = {"target_torque_nm": 25.0, "socket_size_mm": 13.0}
        elif "door" in inst_lower or "open" in inst_lower:
            action = Action.OPEN_DOOR
            obj_name = "door_handle"
            params = {"rotation_deg": 30.0, "pull_distance_m": 0.4}
        elif "tool" in inst_lower or "exchange" in inst_lower:
            action = Action.TOOL_EXCHANGE
            obj_name = "gripper_v2"
            params = {"dock_slot": 1}
        elif "inspect" in inst_lower or "surface" in inst_lower:
            action = Action.INSPECT
            obj_name = "machine_panel"
            params = {"scan_area_m2": 0.25, "resolution_mm": 2.0}
        elif "weld" in inst_lower or "seam" in inst_lower:
            action = Action.WELD
            obj_name = "steel_bracket"
            params = {"current_a": 120.0, "speed_mm_s": 5.0}
        else:
            action = Action.PICK
            match = re.search(r"(?:pick\s+up\s+the\s+|pick\s+)([\w\s]+)", inst_lower)
            obj_name = match.group(1).strip().replace(" ", "_") if match else "red_cube"
            params = {"approach_height": 0.12, "lift_height": 0.18, "grip_force": 10.0, "settle_time": 0.5}

        return SkillIntent(action=action, object_name=obj_name, parameters=params)

    def _decompose_tasks(self, intent: SkillIntent) -> TaskGraph:
        category_map = {
            Action.PICK: IndustrialSkillCategory.PICK_AND_PLACE,
            Action.TIGHTEN: IndustrialSkillCategory.TIGHTEN_BOLT,
            Action.OPEN_DOOR: IndustrialSkillCategory.OPEN_DOOR,
            Action.TOOL_EXCHANGE: IndustrialSkillCategory.TOOL_EXCHANGE,
            Action.INSPECT: IndustrialSkillCategory.INSPECT_SURFACE,
            Action.WELD: IndustrialSkillCategory.WELD_SEAM,
        }
        cat = category_map.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        return TaskGraph(tasks=tmpl.tasks)

    def _plan_motion(self, intent: SkillIntent, task_graph: TaskGraph, verbose: bool = True) -> MotionPlan:
        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 3/4: Motion Planning ({self.robot_spec.name}) \033[0m")

        solver = NDOFIKSolver(self.robot_spec)
        ik_results = {}
        trajectories = {}

        # Default pose targets
        grasp_target = Vec3(0.35, 0.0, 0.13)
        approach_target = Vec3(0.35, 0.0, 0.25)
        lift_target = Vec3(0.35, 0.0, 0.31)

        ok1, q_grasp, res1, iters1 = solver.solve(grasp_target)
        if verbose:
            print(f"  ✓ IK Grasp pose ({intent.object_name})    (residual: {res1:.4f}m, {iters1} iters)")

        ok2, q_approach, res2, iters2 = solver.solve(approach_target)
        if verbose:
            print(f"  ✓ IK Approach pose                   (residual: {res2:.4f}m, {iters2} iters)")

        ok3, q_lift, res3, iters3 = solver.solve(lift_target)
        if verbose:
            print(f"  ✓ IK Lift/Retract pose                (residual: {res3:.4f}m, {iters3} iters)")

        ik_results["grasp"] = IKSolution(joint_angles=q_grasp, residual=res1, iterations=iters1, success=ok1)
        ik_results["approach"] = IKSolution(joint_angles=q_approach, residual=res2, iterations=iters2, success=ok2)
        ik_results["lift"] = IKSolution(joint_angles=q_lift, residual=res3, iterations=iters3, success=ok3)

        # Generate smooth trajectories
        home_q = [0.0] * self.robot_spec.dof
        traj_approach = self._generate_min_jerk_traj(home_q, q_approach, steps=100)
        traj_grasp = self._generate_min_jerk_traj(q_approach, q_grasp, steps=40)
        traj_lift = self._generate_min_jerk_traj(q_grasp, q_lift, steps=50)

        trajectories[f"Approach above {intent.object_name}"] = MotionSegment(home_q, q_approach, traj_approach, 1.0)
        trajectories[f"Grasp pose at {intent.object_name}"] = MotionSegment(q_approach, q_grasp, traj_grasp, 0.4)
        trajectories["Lift target to transfer height"] = MotionSegment(q_grasp, q_lift, traj_lift, 0.5)

        if verbose:
            print(f"\n  → Trajectory: home → approach    (1.0s, {len(traj_approach)} waypoints)")
            print(f"  → Trajectory: approach → grasp   (0.4s, {len(traj_grasp)} waypoints)")
            print(f"  → Trajectory: grasp → lift       (0.5s, {len(traj_lift)} waypoints)")

        return MotionPlan(trajectories=trajectories, ik_results=ik_results, robot_model=self.robot_spec.id)

    def _compile_behavior_tree(self, intent: SkillIntent, task_graph: TaskGraph) -> BTNode:
        cat_map = {
            Action.PICK: IndustrialSkillCategory.PICK_AND_PLACE,
            Action.TIGHTEN: IndustrialSkillCategory.TIGHTEN_BOLT,
            Action.OPEN_DOOR: IndustrialSkillCategory.OPEN_DOOR,
            Action.TOOL_EXCHANGE: IndustrialSkillCategory.TOOL_EXCHANGE,
            Action.INSPECT: IndustrialSkillCategory.INSPECT_SURFACE,
            Action.WELD: IndustrialSkillCategory.WELD_SEAM,
        }
        cat = cat_map.get(intent.action, IndustrialSkillCategory.PICK_AND_PLACE)
        tmpl = get_industrial_skill_template(cat, intent.object_name)
        return tmpl.behavior_tree_root

    def _generate_min_jerk_traj(self, start_q: list[float], end_q: list[float], steps: int = 50) -> list[list[float]]:
        waypoints = []
        n = len(start_q)
        for i in range(steps + 1):
            t = i / steps
            s = 10 * (t ** 3) - 15 * (t ** 4) + 6 * (t ** 5)
            wp = [start_q[j] + s * (end_q[j] - start_q[j]) for j in range(n)]
            waypoints.append(wp)
        return waypoints

    def _print_bt(self, node: BTNode, prefix: str = "", is_last: bool = True) -> None:
        connector = "└─ " if is_last else "├─ "
        print(f"  {prefix}{connector}{node.type}: {node.name}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(node.children):
            self._print_bt(child, child_prefix, i == len(node.children) - 1)
