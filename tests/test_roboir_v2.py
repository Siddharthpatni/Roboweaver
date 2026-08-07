"""
Verification suite for RoboIR v2 additions: task/motion summaries (item 1) and the
capability ontology (item 2) -- docs/COMPILER_ROADMAP.md v2 vision.
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import build_ir


def test_build_ir_without_skill_leaves_summaries_none():
    print("\n[TEST 1] Testing build_ir() without `skill` is unaffected (backward compatible)...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    ir = build_ir(skill.intent, compiler.robot_spec, raw_instruction="test")
    assert ir.task_summary is None
    assert ir.motion_summary is None
    print("  -> task_summary/motion_summary stay None for every existing build_ir() caller [PASSED]")


def test_build_ir_with_skill_populates_real_summaries():
    print("\n[TEST 2] Testing build_ir(skill=...) populates real task/motion summaries...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    ir = build_ir(skill.intent, compiler.robot_spec, raw_instruction="test", skill=skill)

    assert ir.task_summary is not None
    assert ir.task_summary.task_count == len(skill.task_graph.tasks)
    assert list(ir.task_summary.task_types) == [t.type.value for t in skill.task_graph.tasks]

    assert ir.motion_summary is not None
    assert ir.motion_summary.segment_count == len(skill.motion_plan.trajectories)
    expected_waypoints = sum(len(s.waypoints) for s in skill.motion_plan.trajectories.values())
    assert ir.motion_summary.total_waypoints == expected_waypoints
    assert ir.motion_summary.estimated_cycle_time_s > 0
    print(f"  -> task_count={ir.task_summary.task_count}, total_waypoints={ir.motion_summary.total_waypoints} [PASSED]")


def test_compile_with_diagnostics_populates_summaries_from_optimized_skill():
    print("\n[TEST 3] Testing the real compile pipeline attaches summaries from the optimized skill...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)

    assert result.ir.motion_summary is not None
    # WaypointDecimationPass really reduced waypoints -- the IR's summary must
    # reflect the *optimized* skill's waypoint count, not the pre-optimization one.
    optimized_waypoints = sum(len(s.waypoints) for s in result.skill.motion_plan.trajectories.values())
    assert result.ir.motion_summary.total_waypoints == optimized_waypoints
    print(f"  -> RoboIR's motion_summary matches the optimized skill's waypoint count ({optimized_waypoints}) [PASSED]")


def test_capability_claims_are_real_not_arbitrary():
    print("\n[TEST 4] Testing capability claims reflect real declared RobotSpec fields...")
    # Franka Panda declares has_force_torque_sensor=True.
    panda = SkillCompiler(target_robot="franka_panda")
    panda_result = panda.compile_with_diagnostics("Tighten the M8 bolt", verbose=False)
    ft_claim = next(c for c in panda_result.ir.required_capabilities.claims if c.name == "sensing.force_torque")
    assert ft_claim.verified is True
    assert ft_claim.confidence == 1.0

    # Temi declares has_force_torque_sensor=False -- compile fails (RW102) before a
    # CompilationResult is returned, so build the IR directly to inspect the claim.
    from roboweaver.hardware import get_robot_spec
    from roboweaver.types import Action, SkillIntent

    temi_spec = get_robot_spec("temi")
    intent = SkillIntent(action=Action.TIGHTEN, object_name="m8_bolt")
    temi_ir = build_ir(intent, temi_spec, raw_instruction="Tighten the M8 bolt")
    temi_claim = next(c for c in temi_ir.required_capabilities.claims if c.name == "sensing.force_torque")
    assert temi_claim.verified is True  # grounded in the real (False) declared field
    assert temi_claim.confidence == 0.0  # the robot genuinely doesn't have the sensor

    # Perception claims are always honestly unverified -- no perception system exists.
    perception_claims = [c for c in panda_result.ir.required_capabilities.claims if c.source == "unimplemented"]
    assert all(c.verified is False and c.confidence == 0.5 for c in perception_claims)
    print("  -> force_torque claim reflects the real declared field on both robots; perception stays unverified [PASSED]")


if __name__ == "__main__":
    print("=== STARTING ROBOIR V2 (TASK/MOTION SUMMARIES + CAPABILITY ONTOLOGY) VERIFICATION ===")
    test_build_ir_without_skill_leaves_summaries_none()
    test_build_ir_with_skill_populates_real_summaries()
    test_compile_with_diagnostics_populates_summaries_from_optimized_skill()
    test_capability_claims_are_real_not_arbitrary()
    print("\n=== ALL ROBOIR V2 TESTS PASSED SUCCESSFULLY ===")
