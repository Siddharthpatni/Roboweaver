"""
Verification suite for the CompiledSkill optimization/verification pipeline
(optimize/pass_manager.py, optimize/passes.py, optimize/motion_cache.py) --
docs/COMPILER_ROADMAP.md Phase 3/4.
"""

import dataclasses

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.ir import OptimizationLevel, build_ir, check_safety
from roboweaver.optimize import motion_cache
from roboweaver.optimize.pass_manager import SkillPassContext
from roboweaver.optimize.passes import (
    BoundedFormalVerificationPass,
    CompiledSkillVerificationPass,
    WaypointDecimationPass,
    RedundantSegmentElisionPass,
)
from roboweaver.types import TaskGraph, TrajectorySegment


def _real_compiled_skill(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    skill = compiler.compile("Pick up the red cube", verbose=False)
    return compiler, skill


def test_verification_pass_flags_empty_task_graph_as_error():
    print("\n[TEST 1] Testing CompiledSkillVerificationPass flags an empty task_graph (RW501, error)...")
    compiler, skill = _real_compiled_skill()
    empty_skill = dataclasses.replace(skill, task_graph=TaskGraph(tasks=[]))

    ctx = SkillPassContext(skill=empty_skill, robot_spec=compiler.robot_spec)
    result = CompiledSkillVerificationPass().run(ctx)

    rw501 = [d for d in result.diagnostics if d.code == "RW501"]
    assert len(rw501) == 1
    assert rw501[0].severity == "error"
    print("  -> RW501 raised (error) for an empty task_graph [PASSED]")


def test_verification_pass_no_longer_flags_dangling_move_to():
    print("\n[TEST 2] Testing CompiledSkillVerificationPass finds no RW502 now that _plan_motion is generalized...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec)
    result = CompiledSkillVerificationPass().run(ctx)

    # gap-fix batch item 1a fixed the real, pre-existing gap this pass used to
    # surface: compiler.py::_plan_motion now plans one real trajectory per actual
    # MOVE_TO task (optimize/motion_cache.py::compute_motion_primitives), so
    # PICK_AND_PLACE's 4th MOVE_TO task ("Transfer to dropoff location") -- and every
    # other category's MOVE_TO tasks -- now has real motion data. See
    # tests/test_plan_motion_generalization.py for coverage across every category.
    rw502 = [d for d in result.diagnostics if d.code == "RW502"]
    assert rw502 == []
    print("  -> RW502 no longer fires -- every MOVE_TO task has real motion data [PASSED]")


def test_verification_pass_reports_real_cycle_time_metrics():
    print("\n[TEST 3] Testing CompiledSkillVerificationPass computes real timing metrics...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec)
    result = CompiledSkillVerificationPass().run(ctx)

    from roboweaver.types import TaskType
    expected_total = sum(seg.duration for seg in skill.motion_plan.trajectories.values())
    expected_total += sum(
        float(t.params.get("duration", 0.0)) for t in skill.task_graph.tasks if t.type is TaskType.WAIT
    )
    assert abs(result.metrics["estimated_cycle_time_s"] - expected_total) < 1e-3  # metric is round()ed to 4dp
    assert result.modified is False
    print(f"  -> estimated_cycle_time_s == real summed trajectory duration ({expected_total:.3f}s) [PASSED]")


def test_waypoint_decimation_reduces_count_and_stays_safety_verified():
    print("\n[TEST 4] Testing WaypointDecimationPass reduces waypoints without breaking RW304...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec, optimization_level=OptimizationLevel.O1)
    result = WaypointDecimationPass().run(ctx)

    assert result.modified is True
    before = sum(len(s.waypoints) for s in skill.motion_plan.trajectories.values())
    after = sum(len(s.waypoints) for s in result.skill.motion_plan.trajectories.values())
    assert after < before
    assert result.metrics["waypoints_before"] == float(before)
    assert result.metrics["waypoints_after"] == float(after)

    # Re-verify the decimated result through the real safety pass -- proves the
    # decimation is safety-preserving, not just "fewer points".
    ir = build_ir(
        result.skill.intent, compiler.robot_spec, raw_instruction="test", skill=result.skill
    )
    diagnostics = check_safety(ir, compiler.robot_spec)
    assert [d for d in diagnostics if d.code == "RW304"] == []
    print(f"  -> {before} -> {after} waypoints ({result.metrics['pct_reduction']}% reduction), RW304 still clean [PASSED]")


def test_waypoint_decimation_is_noop_at_o0():
    print("\n[TEST 5] Testing WaypointDecimationPass is disabled at -O0...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec, optimization_level=OptimizationLevel.O0)
    assert WaypointDecimationPass().applies(ctx) is False
    print("  -> applies() returns False at O0 [PASSED]")


def test_redundant_segment_elision_collapses_zero_delta_segment():
    print("\n[TEST 6] Testing RedundantSegmentElisionPass collapses a synthetic near-zero-delta segment...")
    compiler, skill = _real_compiled_skill()
    name, seg = next(iter(skill.motion_plan.trajectories.items()))

    # Synthetic: force this segment's end_pose to equal its start_pose -- there is
    # no real registry robot/pose combination that naturally produces this today
    # (proven, not assumed to fire "by luck").
    zero_seg = TrajectorySegment(
        start_pose=seg.start_pose, end_pose=list(seg.start_pose),
        waypoints=seg.waypoints, duration=seg.duration,
    )
    trajectories = dict(skill.motion_plan.trajectories)
    trajectories[name] = zero_seg
    synthetic_skill = dataclasses.replace(
        skill, motion_plan=dataclasses.replace(skill.motion_plan, trajectories=trajectories)
    )

    ctx = SkillPassContext(skill=synthetic_skill, robot_spec=compiler.robot_spec, optimization_level=OptimizationLevel.O1)
    result = RedundantSegmentElisionPass().run(ctx)

    assert result.modified is True
    assert result.metrics["segments_elided"] == 1.0
    collapsed = result.skill.motion_plan.trajectories[name]
    assert collapsed.duration == 0.0
    assert len(collapsed.waypoints) == 2
    print("  -> Zero-delta segment collapsed to 2 waypoints, duration 0.0s [PASSED]")


def test_redundant_segment_elision_is_noop_on_real_demo_poses():
    print("\n[TEST 7] Testing RedundantSegmentElisionPass does not fire on real, non-trivial demo poses...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec, optimization_level=OptimizationLevel.O1)
    result = RedundantSegmentElisionPass().run(ctx)
    assert result.modified is False
    assert result.metrics["segments_elided"] == 0.0
    print("  -> No segments elided for the standard pick/place demo poses [PASSED]")


def test_motion_cache_hits_on_second_call_for_same_robot():
    print("\n[TEST 8] Testing motion_cache memoizes motion primitives per (robot, n_targets)...")
    motion_cache.clear_cache()
    spec = get_robot_spec("ur5e")

    primitives1, hit1 = motion_cache.compute_motion_primitives(spec, 3)
    primitives2, hit2 = motion_cache.compute_motion_primitives(spec, 3)

    assert hit1 is False
    assert hit2 is True
    assert primitives1 is primitives2

    stats = motion_cache.cache_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    print(f"  -> First call missed, second call hit the cache ({stats}) [PASSED]")


def test_compile_with_diagnostics_full_pipeline_end_to_end():
    print("\n[TEST 9] Testing compile_with_diagnostics() runs skill optimization before RoboIR verification...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)

    assert result.skill_pipeline is not None
    assert [r.pass_name for r in result.skill_pipeline.records] == [
        "CompiledSkillVerificationPass", "BoundedFormalVerificationPass",
        "WaypointDecimationPass", "RedundantSegmentElisionPass",
        "CompiledSkillVerificationPass", "BoundedFormalVerificationPass",
    ]
    formal_records = [
        record for record in result.skill_pipeline.records
        if record.pass_name == BoundedFormalVerificationPass.name
    ]
    assert len(formal_records) == 2
    # WaypointDecimationPass really did reduce the waypoint count on the skill that
    # ends up in the CompilationResult -- not a side computation that got discarded.
    before = sum(len(s.waypoints) for s in result.skill_pipeline.initial_skill.motion_plan.trajectories.values())
    after = sum(len(s.waypoints) for s in result.skill.motion_plan.trajectories.values())
    assert after < before
    print(f"  -> Full pipeline: {before} -> {after} waypoints [PASSED]")


def test_duplicate_verification_diagnostics_are_deduped_in_final_list():
    print("\n[TEST 10] Testing a real CompiledSkillVerificationPass diagnostic (from running twice) is deduped...")
    # TIGHTEN_BOLT's real segment durations naturally trigger RW505 (a dominant
    # segment) both times CompiledSkillVerificationPass runs (before and after
    # optimization) -- a real, naturally-occurring case to prove dedup on, not a
    # synthetic one.
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Tighten the M8 bolt", verbose=False)

    raw_rw505_count = len([d for d in result.skill_pipeline.diagnostics() if d.code == "RW505"])
    assert raw_rw505_count == 2  # both CompiledSkillVerificationPass runs really found it

    deduped_rw505_count = len([d for d in result.diagnostics if d.code == "RW505"])
    assert deduped_rw505_count == 1
    print(f"  -> raw trace has {raw_rw505_count} RW505 entries, final diagnostics list has {deduped_rw505_count} [PASSED]")


def test_verification_pass_is_silent_on_a_real_behavior_tree():
    print("\n[TEST 10] Testing CompiledSkillVerificationPass finds no RW506 on a real, well-formed BT...")
    compiler, skill = _real_compiled_skill()
    ctx = SkillPassContext(skill=skill, robot_spec=compiler.robot_spec)
    result = CompiledSkillVerificationPass().run(ctx)
    assert [d for d in result.diagnostics if d.code == "RW506"] == []
    print("  -> No RW506 on the real PICK_AND_PLACE template's behavior tree [PASSED]")


def test_verification_pass_flags_a_malformed_behavior_tree():
    print("\n[TEST 11] Testing CompiledSkillVerificationPass flags RW506 on a synthetic malformed BT (item 10)...")
    from roboweaver.types import BTNode
    compiler, skill = _real_compiled_skill()

    malformed_tree = BTNode(
        type="Sequence", name="root",
        children=[
            BTNode(type="Sequence", name="empty_composite", children=[]),  # zero children
            BTNode(type="Action", name=""),  # empty leaf name
        ],
    )
    malformed_skill = dataclasses.replace(skill, behavior_tree=malformed_tree)

    ctx = SkillPassContext(skill=malformed_skill, robot_spec=compiler.robot_spec)
    result = CompiledSkillVerificationPass().run(ctx)

    rw506 = [d for d in result.diagnostics if d.code == "RW506"]
    assert len(rw506) == 1
    assert rw506[0].severity == "warning"
    assert "empty_composite" in rw506[0].reason or "zero children" in rw506[0].reason
    print(f"  -> RW506 raised: {rw506[0].reason} [PASSED]")


if __name__ == "__main__":
    print("=== STARTING OPTIMIZATION / STATIC ANALYSIS (PHASE 3/4) VERIFICATION ===")
    test_verification_pass_flags_empty_task_graph_as_error()
    test_verification_pass_no_longer_flags_dangling_move_to()
    test_verification_pass_reports_real_cycle_time_metrics()
    test_waypoint_decimation_reduces_count_and_stays_safety_verified()
    test_waypoint_decimation_is_noop_at_o0()
    test_verification_pass_is_silent_on_a_real_behavior_tree()
    test_verification_pass_flags_a_malformed_behavior_tree()
    test_redundant_segment_elision_collapses_zero_delta_segment()
    test_redundant_segment_elision_is_noop_on_real_demo_poses()
    test_motion_cache_hits_on_second_call_for_same_robot()
    test_compile_with_diagnostics_full_pipeline_end_to_end()
    test_duplicate_verification_diagnostics_are_deduped_in_final_list()
    print("\n=== ALL OPTIMIZATION / STATIC ANALYSIS TESTS PASSED SUCCESSFULLY ===")
