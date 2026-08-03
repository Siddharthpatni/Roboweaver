"""
CompiledSkill passes: structural verification plus the first real optimization
passes (docs/COMPILER_ROADMAP.md Phase 3/4).

Deliberately NOT implemented here, and why (see the roadmap for the full accounting):
joint-energy reduction / payload-aware optimization need a dynamics/mass model
RoboWeaver doesn't have (same gap ir/safety.py already documents for torque limits);
"trajectory smoothing" has nothing to smooth -- compiler.py already generates min-jerk
(quintic) trajectories, which are already smooth by construction; gripper-delay
elimination would mean shortening a WAIT task's duration with no real data to justify
the new number, which is exactly the kind of fabricated "optimization" this codebase's
existing passes (ir/safety.py) refuse to produce.
"""

from __future__ import annotations

import dataclasses
from typing import Sequence

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.ir.pass_manager import OptimizationLevel
from roboweaver.optimize.pass_manager import SkillPass, SkillPassContext, SkillPassResult
from roboweaver.types import TaskType, TrajectorySegment

_MIN_WAYPOINTS = 10
_ZERO_DELTA_TOLERANCE = 1e-4  # summed abs joint delta below this = "no real motion"
_DOMINANT_SEGMENT_FRACTION = 0.6


class CompiledSkillVerificationPass(SkillPass):
    """Structural invariant checks on a CompiledSkill -- new logic, not a wrapper.

    RW501 (error): task_graph.tasks is empty -- should never happen, a genuinely
    fatal condition if it does.

    RW502 (warning, not error): a MOVE_TO task's description has no matching entry in
    motion_plan.trajectories or motion_plan.ik_results, meaning
    runtime/engine.py::SkillRuntime.execute() would silently do *nothing* for that
    task (not even an idle step). This turns out to be pervasive, not rare:
    compiler.py::_plan_motion only ever generates the fixed 3-pose pick/place motion
    plan (grasp/approach/lift) regardless of the skill's actual category, so most
    non-pick/place templates' MOVE_TO descriptions (skills/taxonomy.py -- e.g.
    TIGHTEN_BOLT's "Align torque tool with bolt head") never match any motion_plan
    entry, and even PICK_AND_PLACE's own "Transfer to dropoff location" task doesn't.
    Making this an error would refuse to compile nearly every skill in the registry
    for a pre-existing gap this pass merely surfaces -- the same reasoning
    ir/diagnostics.py's RW201 already applies to the (also pervasive) missing
    perception system: real, disclosed, non-blocking, not fabricated as fixed and
    not swept under the rug as passing.

    Also computes a real, non-fabricated timing-analysis signal: if one trajectory
    segment's duration exceeds 60% of the estimated total cycle time, flags it as
    dominating (RW505, warning) -- both numbers come directly from the compiled
    skill's own trajectory durations and WAIT task params, nothing estimated.

    Runs both before and after the optimization passes in compiler.py's default
    pipeline: a regression guard on the way in, proof the optimizer didn't break
    structure on the way out -- the same verify-before/after pattern
    ir/passes.py::RoboIRVerificationPass established for RoboIR."""

    name = "CompiledSkillVerificationPass"

    def run(self, ctx: SkillPassContext) -> SkillPassResult:
        skill = ctx.skill
        diagnostics: list[CompilerDiagnostic] = []

        if not skill.task_graph.tasks:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW501",
                    severity="error",
                    message="CompiledSkill has an empty task_graph.",
                    reason="task_graph.tasks is empty -- there is nothing to execute.",
                    required_capability=None,
                    fixes=[
                        "This indicates a bug in whichever stage produced this "
                        "CompiledSkill (compile() or an optimization pass) -- not a "
                        "user-fixable input.",
                    ],
                )
            )

        dangling = [
            task.description for task in skill.task_graph.tasks
            if task.type is TaskType.MOVE_TO
            and task.description not in skill.motion_plan.trajectories
            and task.description not in skill.motion_plan.ik_results
        ]
        if dangling:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW502",
                    severity="warning",
                    message=(
                        f"{len(dangling)} MOVE_TO task(s) have no matching motion_plan "
                        f"entry and will silently no-op during execution."
                    ),
                    reason=(
                        f"Task description(s) {dangling!r} match no key in "
                        f"motion_plan.trajectories or motion_plan.ik_results."
                    ),
                    required_capability=None,
                    fixes=[
                        "compiler.py::_plan_motion currently only plans the fixed "
                        "3-pose pick/place motion regardless of skill category -- "
                        "extend it (or add a category-specific motion planner) to "
                        "produce a trajectory/IK entry for every MOVE_TO task this "
                        "skill's template declares.",
                    ],
                )
            )

        total_time = sum(seg.duration for seg in skill.motion_plan.trajectories.values())
        total_time += sum(
            float(task.params.get("duration", 0.0))
            for task in skill.task_graph.tasks
            if task.type is TaskType.WAIT
        )
        metrics: dict[str, float] = {
            "dangling_move_to": float(len(dangling)),
            "estimated_cycle_time_s": round(total_time, 4),
        }

        if total_time > 0:
            for seg_name, seg in skill.motion_plan.trajectories.items():
                fraction = seg.duration / total_time
                if fraction > _DOMINANT_SEGMENT_FRACTION:
                    diagnostics.append(
                        CompilerDiagnostic(
                            code="RW505",
                            severity="warning",
                            message=f"Trajectory segment '{seg_name}' dominates estimated cycle time.",
                            reason=(
                                f"'{seg_name}' is {seg.duration:.2f}s of an estimated "
                                f"{total_time:.2f}s total cycle time ({fraction * 100:.0f}%)."
                            ),
                            required_capability=None,
                            fixes=[
                                "Check whether this segment's velocity-limit-bound "
                                "duration (compiler.py::_min_safe_duration) can be "
                                "reduced, or whether the path itself can be shortened.",
                            ],
                        )
                    )

        return SkillPassResult(skill=skill, diagnostics=diagnostics, metrics=metrics, modified=False)


class WaypointDecimationPass(SkillPass):
    """Real trajectory-compression optimization: for each segment, keeps every Nth
    waypoint (uniform stride) at the largest stride that (a) evenly divides the
    segment's waypoint count minus one -- so the true final waypoint always lands
    exactly on-stride and every kept interval spans an identical amount of time,
    keeping ir/safety.py::_check_velocity_limits's uniform-time-stepping assumption
    valid on the decimated result, not just the original -- (b) leaves at least
    _MIN_WAYPOINTS waypoints, and (c) keeps every joint's finite-difference velocity
    between kept waypoints within robot_spec.get_max_velocities(), computed here
    in-pass with the exact same formula ir/safety.py's RW304 check uses, so the
    choice is self-verifying rather than assumed. Rules out non-uniform methods
    (e.g. Ramer-Douglas-Peucker) for exactly this reason -- see
    docs/COMPILER_ROADMAP.md Phase 4.

    Gated by optimization_level: a no-op at O0, matching GCC/LLVM convention -- the
    first pass giving OptimizationLevel something real to gate."""

    name = "WaypointDecimationPass"

    def applies(self, ctx: SkillPassContext) -> bool:
        return ctx.optimization_level != OptimizationLevel.O0

    def run(self, ctx: SkillPassContext) -> SkillPassResult:
        skill = ctx.skill
        max_vels = ctx.robot_spec.get_max_velocities()
        dof = ctx.robot_spec.dof

        new_trajectories: dict[str, TrajectorySegment] = {}
        waypoints_before = 0
        waypoints_after = 0
        segments_changed = 0

        for name, seg in skill.motion_plan.trajectories.items():
            waypoints_before += len(seg.waypoints)
            stride = self._largest_safe_stride(seg, max_vels, dof)
            if stride <= 1:
                new_trajectories[name] = seg
                waypoints_after += len(seg.waypoints)
                continue

            decimated = list(seg.waypoints[::stride])
            new_trajectories[name] = TrajectorySegment(
                start_pose=seg.start_pose, end_pose=seg.end_pose,
                waypoints=decimated, duration=seg.duration,
            )
            waypoints_after += len(decimated)
            segments_changed += 1

        if segments_changed == 0:
            return SkillPassResult(
                skill=skill,
                metrics={
                    "waypoints_before": float(waypoints_before),
                    "waypoints_after": float(waypoints_after),
                    "pct_reduction": 0.0,
                },
                modified=False,
            )

        new_motion_plan = dataclasses.replace(skill.motion_plan, trajectories=new_trajectories)
        new_skill = dataclasses.replace(skill, motion_plan=new_motion_plan)
        pct_reduction = (1 - waypoints_after / waypoints_before) * 100 if waypoints_before else 0.0

        return SkillPassResult(
            skill=new_skill,
            metrics={
                "waypoints_before": float(waypoints_before),
                "waypoints_after": float(waypoints_after),
                "pct_reduction": round(pct_reduction, 2),
                "segments_changed": float(segments_changed),
            },
            modified=True,
        )

    @staticmethod
    def _largest_safe_stride(seg: TrajectorySegment, max_vels: Sequence[float], dof: int) -> int:
        n = len(seg.waypoints)
        if n <= _MIN_WAYPOINTS or seg.duration <= 0:
            return 1
        span = n - 1  # number of original uniform-time intervals
        dt_orig = seg.duration / span

        candidate_strides = [s for s in range(span, 1, -1) if span % s == 0]
        for stride in candidate_strides:
            kept_count = span // stride + 1
            if kept_count < _MIN_WAYPOINTS:
                continue
            dt_new = dt_orig * stride
            sampled = seg.waypoints[::stride]
            if WaypointDecimationPass._within_velocity_limits(sampled, dt_new, max_vels, dof):
                return stride
        return 1

    @staticmethod
    def _within_velocity_limits(
        waypoints: Sequence[Sequence[float]], dt: float, max_vels: Sequence[float], dof: int
    ) -> bool:
        for i in range(len(waypoints) - 1):
            a, b = waypoints[i], waypoints[i + 1]
            for j in range(min(len(a), len(b), dof, len(max_vels))):
                if max_vels[j] <= 0:
                    continue
                if abs(b[j] - a[j]) / dt > max_vels[j]:
                    return False
        return True


class RedundantSegmentElisionPass(SkillPass):
    """Real optimization: collapses a trajectory segment to just its two endpoints
    (and zero duration) when start_pose and end_pose are within
    _ZERO_DELTA_TOLERANCE of each other -- there is no real motion to execute. Won't
    fire on today's standard demo poses (their deltas are real and non-trivial) --
    proven with a synthetic near-zero-delta segment in
    tests/test_optimize_passes.py, not relying on it firing "by luck" on registry
    robots. Gated by optimization_level -- a no-op at O0."""

    name = "RedundantSegmentElisionPass"

    def applies(self, ctx: SkillPassContext) -> bool:
        return ctx.optimization_level != OptimizationLevel.O0

    def run(self, ctx: SkillPassContext) -> SkillPassResult:
        skill = ctx.skill
        new_trajectories: dict[str, TrajectorySegment] = {}
        segments_elided = 0
        time_saved = 0.0

        for name, seg in skill.motion_plan.trajectories.items():
            delta = sum(abs(a - b) for a, b in zip(seg.start_pose, seg.end_pose))
            if delta < _ZERO_DELTA_TOLERANCE and len(seg.waypoints) > 2:
                segments_elided += 1
                time_saved += seg.duration
                new_trajectories[name] = TrajectorySegment(
                    start_pose=seg.start_pose, end_pose=seg.end_pose,
                    waypoints=[seg.waypoints[0], seg.waypoints[-1]], duration=0.0,
                )
            else:
                new_trajectories[name] = seg

        if segments_elided == 0:
            return SkillPassResult(
                skill=skill, metrics={"segments_elided": 0.0, "time_saved_s": 0.0}, modified=False,
            )

        new_motion_plan = dataclasses.replace(skill.motion_plan, trajectories=new_trajectories)
        new_skill = dataclasses.replace(skill, motion_plan=new_motion_plan)
        return SkillPassResult(
            skill=new_skill,
            metrics={"segments_elided": float(segments_elided), "time_saved_s": round(time_saved, 4)},
            modified=True,
        )
