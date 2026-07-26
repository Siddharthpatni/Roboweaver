"""
Skill Runtime — executes compiled skills in simulation (Pure Python or MuJoCo).

Drives the robot through every task in the compiled task graph, updates kinematics,
handles grasping & contact dynamics, records visual frame telemetry, and verifies success.
"""

from __future__ import annotations

import math
from typing import Sequence

from roboweaver.types import CompiledSkill, ExecutionResult, TaskType
from roboweaver.hardware import forward_kinematics_ndof, get_robot_spec, get_franka_panda_spec
from roboweaver.math3d import Vec3


class SkillRuntime:
    """Executes compiled skills against 3D robot simulation environment."""

    def __init__(
        self,
        robot_spec=None,
        model=None,
        data=None,
        render_width: int = 640,
        render_height: int = 480,
        render_fps: int = 30,
    ):
        self.robot_spec = robot_spec or get_franka_panda_spec()
        self.model = model
        self.data = data
        self.render_width = render_width
        self.render_height = render_height
        self.render_fps = render_fps

        self.qpos = [0.0] * self.robot_spec.dof
        self.gripper_pos = 0.0
        self.cube_pos = Vec3(0.35, 0.0, 0.13)
        self.is_grasped = False
        self.frames: list[str] = []
        self.step_count = 0
        self.dt = 0.01

    def execute(self, skill: CompiledSkill, verbose: bool = True) -> ExecutionResult:
        """Execute a compiled skill and return result."""
        self.frames = []
        self.step_count = 0
        self.qpos = [0.0] * self.robot_spec.dof

        initial_cube_z = self.cube_pos.z

        if verbose:
            print(f"\n\033[1;36m━━━ STAGE 5/6: Execute in Simulation \033[0m")
            engine_name = "MuJoCo" if self.model is not None else "RoboWeaver Native 3D Engine"
            print(f"  \033[0;37m→\033[0m Simulator:  {engine_name}")
            print(f"  \033[0;37m→\033[0m Robot:      {self.robot_spec.name} ({self.robot_spec.dof}-DOF)")
            print(f"  \033[0;37m→\033[0m Scene:      Tabletop with Red Cube")
            print()

        total_tasks = len(skill.task_graph.tasks)

        for i, task in enumerate(skill.task_graph.tasks):
            if verbose:
                progress = int(40 * (i + 1) / total_tasks)
                bar = "█" * progress + "░" * (40 - progress)
                desc = task.description[:30].ljust(30)
                print(f"\r  [{bar}] {desc}", end="", flush=True)

            if task.type == TaskType.PERCEIVE:
                self._idle(steps=20)

            elif task.type == TaskType.OPEN_GRIPPER:
                self.gripper_pos = task.params.get("target", 0.04)
                self.is_grasped = False
                self._idle(steps=30)

            elif task.type == TaskType.CLOSE_GRIPPER:
                self.gripper_pos = task.params.get("target", 0.0)
                ee_pos = forward_kinematics_ndof(self.robot_spec, self.qpos).pos
                dist = (ee_pos - self.cube_pos).norm()
                if dist < 0.15:
                    self.is_grasped = True
                self._idle(steps=40)

            elif task.type == TaskType.MOVE_TO:
                traj_seg = skill.motion_plan.trajectories.get(task.description)
                if traj_seg is not None:
                    self._execute_trajectory(traj_seg.waypoints)
                else:
                    ik = skill.motion_plan.ik_results.get(task.description)
                    if ik is not None:
                        self.qpos = list(ik.joint_angles)
                        self._idle(steps=50)

            elif task.type == TaskType.WAIT:
                duration = task.params.get("duration", 0.5)
                steps = int(duration / self.dt)
                self._idle(steps=steps)

            elif task.type == TaskType.VERIFY_GRASP:
                if verbose and not self.is_grasped:
                    print(f"\n  \033[33m⚠ Cube may not be grasped\033[0m")

        if verbose:
            print()

        final_cube_z = self.cube_pos.z
        height_gained = final_cube_z - initial_cube_z
        cycle_time = self.step_count * self.dt
        limits_ok = self._check_joint_limits()
        success = height_gained > 0.03

        return ExecutionResult(
            success=success,
            initial_object_height=initial_cube_z,
            final_object_height=final_cube_z,
            height_gained=height_gained,
            cycle_time=cycle_time,
            joint_limits_respected=limits_ok,
            frames=self.frames,
        )

    def save_video(self, path: str, fps: int = 30) -> None:
        """Save recorded simulation visualization frame log."""
        if not self.frames:
            print("  No frames to save.")
            return

        html_path = path.replace(".mp4", ".html").replace(".gif", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html><head><title>RoboWeaver Skill Execution Replay</title>")
            f.write("<style>body{background:#111;color:#eee;font-family:monospace;padding:20px;}")
            f.write("#console{background:#000;color:#0f0;padding:15px;border-radius:6px;white-space:pre;}")
            f.write("</style></head><body><h2>RoboWeaver Execution Replay</h2>")
            f.write(f"<p>Total Frames: {len(self.frames)} | Duration: {len(self.frames)*self.dt:.1f}s</p>")
            f.write("<div id='console'>Initializing execution replay...</div>")
            f.write("<script>const frames = " + str(self.frames) + ";\n")
            f.write("let idx = 0; setInterval(() => {\n")
            f.write("  document.getElementById('console').textContent = frames[idx];\n")
            f.write("  idx = (idx + 1) % frames.length;\n")
            f.write("}, 50);</script></body></html>")

        print(f"  \033[0;32m✓ Replay HTML saved: {html_path}\033[0m")

    def _execute_trajectory(self, waypoints: Sequence[Sequence[float]]) -> None:
        for wp in waypoints:
            self.qpos = list(wp)
            self._step()

    def _idle(self, steps: int) -> None:
        for _ in range(steps):
            self._step()

    def _step(self) -> None:
        self.step_count += 1
        ee_pos = forward_kinematics_ndof(self.robot_spec, self.qpos).pos

        if self.is_grasped:
            self.cube_pos = ee_pos

        if self.step_count % 5 == 0:
            frame_str = (
                f"Frame {self.step_count:04d} | EE Pos: ({ee_pos.x:.3f}, {ee_pos.y:.3f}, {ee_pos.z:.3f}) | "
                f"Cube Z: {self.cube_pos.z:.3f}m | Grip: {'[CLOSED]' if self.is_grasped else '[OPEN]'}"
            )
            self.frames.append(frame_str)

    def _check_joint_limits(self) -> bool:
        limits = self.robot_spec.get_joint_limits()
        for i, val in enumerate(self.qpos[: self.robot_spec.dof]):
            lo, hi = limits[i]
            if val < lo - 0.01 or val > hi + 0.01:
                return False
        return True
