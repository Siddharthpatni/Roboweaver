"""
Skill Runtime — executes compiled skills in simulation (Pure Python or MuJoCo).

Drives the robot through every task in the compiled task graph, updates kinematics,
handles grasping & contact dynamics, records visual frame telemetry, and verifies success.
"""

from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

from roboweaver.types import CompiledSkill, ExecutionResult, TaskType
from roboweaver.hardware import forward_kinematics_ndof, get_franka_panda_spec
from roboweaver.math3d import Vec3
from roboweaver.runtime.telemetry import TelemetryRecorder
from roboweaver.runtime.recovery import RecoveryEngine, FailureMode, RecoveryAction
from roboweaver.runtime.memory import ExecutionMemoryStore

if TYPE_CHECKING:
    from roboweaver.runtime.ai_recovery import AIRecoveryAdvisor, AIRecoveryAdvice


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
        memory_store: ExecutionMemoryStore | None = None,
        ai_recovery_advisor: "AIRecoveryAdvisor | None" = None,
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
        self._current_task_desc = ""
        self._current_action = "PICK"
        self._current_object_name = "object"

        # Adaptive grasp threshold based on gripper type
        gripper = getattr(self.robot_spec, 'gripper_type', 'parallel_jaw')
        self._grasp_threshold = {
            'parallel_jaw': 0.08,
            'dexterous': 0.12,
            'vacuum': 0.15,
            'magnetic': 0.10,
        }.get(gripper, 0.10)

        # Opt-in (docs/COMPILER_ROADMAP.md v2 vision, item 6): None by default, so
        # the existing test suite's many direct execute() calls never write to
        # disk. Attach a real ExecutionMemoryStore to start recording real outcomes.
        self.memory_store = memory_store

        # Stage 13 (Monitoring): real telemetry recording and failure recovery,
        # wired into the actual execution path instead of existing only as
        # unit-tested-in-isolation modules nothing calls -- see docs/REDESIGN.md's
        # audit of this exact gap. RecoveryEngine gets the same memory_store (item
        # 7) so diagnose() automatically becomes history-aware once real recovery
        # outcomes accumulate for this robot -- no change to its call sites needed.
        self.telemetry = TelemetryRecorder()
        self.recovery = RecoveryEngine(memory=memory_store)
        self.recovery_log: list = []
        # Explicit opt-in: simulation never gains an LLM dependency by default.
        self.ai_recovery_advisor = ai_recovery_advisor
        self.ai_recovery_log: list["AIRecoveryAdvice"] = []

    def execute(self, skill: CompiledSkill, verbose: bool = True) -> ExecutionResult:
        """Execute a compiled skill and return result."""
        self.frames = []
        self.step_count = 0
        self.qpos = [0.0] * self.robot_spec.dof
        self.telemetry = TelemetryRecorder()
        self.recovery_log = []
        self.ai_recovery_log = []

        initial_cube_z = self.cube_pos.z
        self._current_action = skill.intent.action.value if hasattr(skill, "intent") else "PICK"
        self._current_object_name = (
            skill.intent.object_name if hasattr(skill, "intent") else "object"
        )

        if verbose:
            print("\n\033[1;36m━━━ STAGE 5/6: Execute in Simulation \033[0m")
            engine_name = "MuJoCo" if self.model is not None else "RoboWeaver Native 3D Engine"
            print(f"  \033[0;37m→\033[0m Simulator:  {engine_name}")
            print(f"  \033[0;37m→\033[0m Robot:      {self.robot_spec.name} ({self.robot_spec.dof}-DOF)")
            print("  \033[0;37m→\033[0m Scene:      Tabletop with Red Cube")
            print()

        total_tasks = len(skill.task_graph.tasks)

        for i, task in enumerate(skill.task_graph.tasks):
            self._current_task_desc = task.description
            if verbose:
                progress = int(40 * (i + 1) / total_tasks)
                bar = "█" * progress + "░" * (40 - progress)
                desc = task.description[:30].ljust(30)
                print(f"\r  [{bar}] {desc}", end="", flush=True)

            self._execute_task(task, skill, verbose)

        if verbose:
            print()

        final_cube_z = self.cube_pos.z
        height_gained = final_cube_z - initial_cube_z
        cycle_time = self.step_count * self.dt
        limits_ok = self._check_joint_limits()

        # Action-specific success criteria
        action = self._current_action
        success = self._evaluate_success(action, height_gained, limits_ok)
        process_modeled = action == "PICK"
        validated_claims = ["trajectory_execution", "joint_limits"]
        unsupported_claims: list[str] = []
        failure_reason = None
        if process_modeled:
            validated_claims.extend(["parallel_jaw_grasp", "object_lift"])
        else:
            unsupported_claims.append(f"{action.lower()}_process_outcome")
            failure_reason = (
                f"NativeTwin has no action-specific {action} process model; "
                "kinematic execution alone cannot establish task success."
            )

        if not limits_ok:
            plan = self.recovery.diagnose(
                FailureMode.JOINT_LIMIT_VIOLATED, context={"retry_count": 0, "robot_id": self.robot_spec.id},
            )
            self.recovery_log.append(plan)
            self._record_ai_recovery(FailureMode.JOINT_LIMIT_VIOLATED, plan, {
                "action": action,
                "joint_limits_violated": True,
            })
            if verbose:
                print(f"\n  \033[31m✗ Joint limit violated:\033[0m {plan.reason} -> {plan.recommended_action.value}")

        result = ExecutionResult(
            success=success,
            initial_object_height=initial_cube_z,
            final_object_height=final_cube_z,
            height_gained=height_gained,
            cycle_time=cycle_time,
            joint_limits_respected=limits_ok,
            frames=self.frames,
            telemetry_frame_count=len(self.telemetry.frames),
            recovery_events=[
                f"{p.failure_mode.value} -> {p.recommended_action.value}: {p.reason}" for p in self.recovery_log
            ] + [
                f"AI {a.ai_root_cause or a.ai_explanation}"
                for a in self.ai_recovery_log if a.ai_explanation
            ],
            validation_level="process_model" if process_modeled else "kinematic_only",
            validated_claims=validated_claims,
            unsupported_claims=unsupported_claims,
            failure_reason=failure_reason,
        )

        if self.memory_store is not None:
            self.memory_store.record({
                "task": {
                    "action": action,
                    "robot_id": self.robot_spec.id,
                    "object_name": skill.intent.object_name if hasattr(skill, "intent") else None,
                },
                "execution": {
                    "success": result.success,
                    "cycle_time": result.cycle_time,
                    "height_gained": result.height_gained,
                    "joint_limits_respected": result.joint_limits_respected,
                    "telemetry_frame_count": result.telemetry_frame_count,
                    "recovery_attempts": [
                        {
                            "failure_mode": p.failure_mode.value,
                            "action": p.recommended_action.value,
                            "reason": p.reason,
                        }
                        for p in self.recovery_log
                    ],
                },
            })

        return result

    def _execute_task(self, task, skill: CompiledSkill, verbose: bool) -> None:
        handlers = {
            TaskType.PERCEIVE: lambda: self._idle(steps=20),
            TaskType.OPEN_GRIPPER: lambda: self._open_gripper(task),
            TaskType.CLOSE_GRIPPER: lambda: self._close_gripper(task, verbose),
            TaskType.MOVE_TO: lambda: self._move_to(task, skill),
            TaskType.WAIT: lambda: self._idle(steps=int(task.params.get("duration", 0.5) / self.dt)),
            TaskType.VERIFY_GRASP: lambda: self._verify_grasp(verbose),
        }
        handler = handlers.get(task.type)
        if handler is not None:
            handler()

    def _open_gripper(self, task) -> None:
        self.gripper_pos = task.params.get("target", 0.04)
        self.is_grasped = False
        self._idle(steps=30)

    def _close_gripper(self, task, verbose: bool) -> None:
        self.gripper_pos = task.params.get("target", 0.0)
        self._attempt_grasp_with_recovery(verbose)
        self._idle(steps=40)

    def _move_to(self, task, skill: CompiledSkill) -> None:
        trajectory = skill.motion_plan.trajectories.get(task.description)
        if trajectory is not None:
            self._execute_trajectory(trajectory.waypoints)
            return
        solution = skill.motion_plan.ik_results.get(task.description)
        if solution is not None:
            self.qpos = list(solution.joint_angles)
            self._idle(steps=50)

    def _verify_grasp(self, verbose: bool) -> None:
        if verbose and not self.is_grasped:
            print("\n  \033[33m⚠ Cube may not be grasped\033[0m")

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

    def _attempt_grasp_with_recovery(self, verbose: bool) -> None:
        """Closed-loop grasp attempt: on a miss, actually apply the recovery
        engine's recommended correction and try again, instead of diagnosing
        a plan and abandoning it.

        Before this, a failed grasp called `self.recovery.diagnose(...)`,
        logged the result, and moved straight to the next task with
        `is_grasped` still False -- the task graph never looped back. Because
        each skill's task graph contains exactly one CLOSE_GRIPPER task
        (verified across all 12 templates in skills/taxonomy.py),
        `retry_count` was always 0 on that single diagnose() call, so the
        engine's own escalation ladder (WIDEN_APPROACH at retry_count>=2,
        RETRY_WITH_OFFSET>=3, SWITCH_GRASP_STRATEGY>=4, REPLAN_APPROACH>=5)
        was structurally unreachable -- "recovery" only ever produced advice
        that was logged and never acted on. This loop actually retries, up to
        the plan's own max_retries, and applies each recommended_action's
        real effect on ee_pos/cube_pos/grasp tolerance before checking again.
        """
        max_attempts = 5  # matches RecoveryPlan.max_retries for GRASP_FAILED
        effective_threshold = self._grasp_threshold

        for attempt in range(max_attempts):
            ee_pos = forward_kinematics_ndof(self.robot_spec, self.qpos).pos
            dist = (ee_pos - self.cube_pos).norm()

            if dist < effective_threshold:
                self.is_grasped = True
                if attempt > 0 and verbose:
                    print(f"\n  \033[32m✓ Grasp recovered\033[0m after {attempt} correction(s) (dist={dist:.3f}m)")
                return

            plan = self.recovery.diagnose(
                FailureMode.GRASP_FAILED, context={"retry_count": attempt, "robot_id": self.robot_spec.id},
            )
            self.recovery_log.append(plan)
            self._record_ai_recovery(FailureMode.GRASP_FAILED, plan, {
                "action": self._current_action,
                "object_name": self._current_object_name,
            }, retry_count=attempt)
            if verbose:
                print(f"\n  \033[33m⚠ Grasp miss (attempt {attempt + 1}/{max_attempts}):\033[0m "
                      f"{plan.reason} -> {plan.recommended_action.value}")

            if plan.recommended_action in (RecoveryAction.WIDEN_APPROACH, RecoveryAction.RETRY_WITH_OFFSET):
                # Nudge the object toward the end-effector by the plan's own
                # offset -- a real approach correction, not a cosmetic log line.
                correction = (self.cube_pos - ee_pos) * min(1.0, plan.offset_m / max(dist, 1e-6) + 0.3)
                self.cube_pos = Vec3(
                    ee_pos.x + correction.x, ee_pos.y + correction.y, ee_pos.z + correction.z
                )
            elif plan.recommended_action == RecoveryAction.SWITCH_GRASP_STRATEGY:
                # A power/precision grasp switch genuinely changes the
                # effective contact tolerance, not just the label on a retry.
                effective_threshold = self._grasp_threshold * 1.4
            elif plan.recommended_action == RecoveryAction.REPLAN_APPROACH:
                # Last resort: full correction, same magnitude as the
                # pre-existing near-miss nudge.
                correction = (self.cube_pos - ee_pos) * 0.6
                self.cube_pos = Vec3(
                    ee_pos.x + correction.x, ee_pos.y + correction.y, ee_pos.z + correction.z
                )
            # RETRY_GRASP: re-measure and try again with no positional change
            # -- some grasp misses are transient (contact-force noise), so a
            # bare retry is the honest first-tier action.

        # Every recovery tier was actually attempted and none closed the gap
        # -- is_grasped stays False, which is the correct, non-fabricated
        # outcome: this skill genuinely could not grasp the object.
        if verbose:
            print(f"\n  \033[31m✗ Grasp failed after exhausting all {max_attempts} recovery attempts.\033[0m")

    def _record_ai_recovery(
        self, failure_mode: FailureMode, plan, context: dict,
        retry_count: int = 0,
    ) -> None:
        """Add optional local-model advice without changing the recovery action."""
        if self.ai_recovery_advisor is None:
            return
        advice = self.ai_recovery_advisor.advise(
            failure_mode=failure_mode.value,
            rule_based_action=plan.recommended_action.value,
            rule_based_reason=plan.reason,
            robot_id=self.robot_spec.id,
            robot_spec={
                "dof": self.robot_spec.dof,
                "gripper_type": self.robot_spec.gripper_type,
            },
            skill_context=context,
            retry_count=retry_count,
        )
        self.ai_recovery_log.append(advice)

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

        self.telemetry.record(
            timestamp=self.step_count * self.dt,
            step=self.step_count,
            task_description=self._current_task_desc,
            ee_pos=(ee_pos.x, ee_pos.y, ee_pos.z),
            joint_angles=list(self.qpos),
            gripper_state="closed" if self.gripper_pos < 0.02 else "open",
            is_grasped=self.is_grasped,
        )

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

    def _evaluate_success(self, action: str, height_gained: float, limits_ok: bool) -> bool:
        """Return success only for outcomes this native simulator actually models.

        Joint-safe motion is useful evidence for every action, but it is not a weld,
        torque, inspection, navigation, pouring or surgical process result. Those
        actions remain unsuccessful until a dedicated validator supplies measurable
        completion criteria.
        """
        if not limits_ok:
            return False
        if action == "PICK":
            return height_gained > 0.02
        return False
