"""
Verification suite for the Pass Manager (ir/pass_manager.py), the passes built on top
of it (ir/passes.py), IR diffing (ir/diff.py), and RoboIR's new frozen/immutable
dataclasses (ir/schema.py) -- docs/COMPILER_ROADMAP.md Phase 2.

Regression bar: every pre-existing diagnostic-shape assertion this codebase relies on
(RW102 first for a missing capability, RW201 warnings for perception, etc.) must still
hold now that CapabilityPass/SafetyPass run through PassManager instead of being
called directly by compiler.py.
"""

import dataclasses

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.ir import (
    SkillCompilationError,
    OptimizationLevel,
    PassManager,
    PassContext,
    PassResult,
    CompilerPass,
    RoboIRVerificationPass,
    CapabilityPass,
    SafetyPass,
    build_ir,
    check_required_capabilities,
    check_safety,
    diff_ir,
    diff_trace,
)


def _compile_ir(robot_id: str, instruction: str = "Pick up the red cube"):
    """Real skill + RoboIR for a robot, via the same code path build_ir() itself uses."""
    compiler = SkillCompiler(target_robot=robot_id)
    skill = compiler.compile(instruction, verbose=False)
    ir = build_ir(skill.intent, compiler.robot_spec, raw_instruction=instruction)
    return compiler, skill, ir


def test_roboir_is_frozen():
    print("\n[TEST 1] Testing RoboIR (and nested dataclasses) reject field reassignment...")
    _, _, ir = _compile_ir("franka_panda")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ir.action = "SOMETHING_ELSE"
    with pytest.raises(dataclasses.FrozenInstanceError):
        ir.execution.dof = 99
    print("  -> ir.action and ir.execution.dof reassignment both raise FrozenInstanceError [PASSED]")


def test_pass_manager_runs_passes_in_order_and_builds_trace():
    print("\n[TEST 2] Testing PassManager runs passes in order and records a full trace...")
    compiler, skill, ir = _compile_ir("franka_panda")
    pm = PassManager([RoboIRVerificationPass(), CapabilityPass(), SafetyPass()])
    trace = pm.run(ir, skill, compiler.robot_spec, OptimizationLevel.O1)

    assert [r.pass_name for r in trace.records] == [
        "RoboIRVerificationPass", "CapabilityPass", "SafetyPass",
    ]
    assert all(r.timing_s >= 0.0 for r in trace.records)
    assert trace.initial_ir is ir
    assert trace.snapshot_at(0) is ir
    assert trace.snapshot_at(3) is trace.final_ir
    with pytest.raises(IndexError):
        trace.snapshot_at(4)
    print(f"  -> 3 passes ran in order, trace has {len(trace.records)} records, snapshots resolve [PASSED]")


def test_verification_pass_is_silent_on_a_real_build_ir_output():
    print("\n[TEST 3] Testing RoboIRVerificationPass is silent on a real, well-formed RoboIR...")
    compiler, skill, ir = _compile_ir("franka_panda")
    ctx = PassContext(ir=ir, skill=skill, robot_spec=compiler.robot_spec)
    result = RoboIRVerificationPass().run(ctx)
    assert result.diagnostics == []
    assert result.modified is False
    print("  -> Zero diagnostics on build_ir()'s own output [PASSED]")


def test_verification_pass_flags_a_deliberately_malformed_ir():
    print("\n[TEST 4] Testing RoboIRVerificationPass catches a real structural violation...")
    compiler, skill, ir = _compile_ir("franka_panda")
    bad_execution = dataclasses.replace(ir.execution, dof=ir.execution.dof + 1)
    bad_ir = dataclasses.replace(ir, execution=bad_execution)

    ctx = PassContext(ir=bad_ir, skill=skill, robot_spec=compiler.robot_spec)
    result = RoboIRVerificationPass().run(ctx)

    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "RW401"
    assert result.diagnostics[0].severity == "error"
    assert "dof" in result.diagnostics[0].reason
    print("  -> RW401 raised for an execution.dof mismatch against the target robot [PASSED]")


def test_capability_pass_matches_direct_function_call():
    print("\n[TEST 5] Testing CapabilityPass is a faithful wrap of check_required_capabilities()...")
    compiler, skill, ir = _compile_ir("temi", "Tighten the M8 bolt")
    direct = check_required_capabilities(ir, compiler.robot_spec)
    via_pass = CapabilityPass().run(
        PassContext(ir=ir, skill=skill, robot_spec=compiler.robot_spec)
    ).diagnostics
    assert via_pass == direct
    assert any(d.code == "RW102" for d in via_pass)
    print("  -> CapabilityPass produces identical diagnostics to the direct function call [PASSED]")


def test_safety_pass_matches_direct_function_call():
    print("\n[TEST 6] Testing SafetyPass is a faithful wrap of check_safety()...")
    compiler, skill, ir = _compile_ir("franka_panda")
    direct = check_safety(skill, ir, compiler.robot_spec)
    via_pass = SafetyPass().run(
        PassContext(ir=ir, skill=skill, robot_spec=compiler.robot_spec)
    ).diagnostics
    assert via_pass == direct
    print(f"  -> SafetyPass produces identical diagnostics to the direct function call ({len(direct)}) [PASSED]")


class _StripLastSafetyCheckPass(CompilerPass):
    """Test-only IR-mutating pass -- proves the PassManager's generation mechanism and
    ir/diff.py's diffing actually work end-to-end, without shipping a fabricated
    production "optimization" pass (no real one exists yet -- Phase 4)."""

    name = "StripLastSafetyCheckPass"

    def run(self, ctx: PassContext) -> PassResult:
        new_checks = list(ctx.ir.verification.safety_checks[:-1])
        new_verification = dataclasses.replace(ctx.ir.verification, safety_checks=new_checks)
        new_ir = dataclasses.replace(ctx.ir, verification=new_verification)
        return PassResult(ir=new_ir, modified=True)


def test_ir_mutating_pass_produces_a_new_generation_and_a_real_diff():
    print("\n[TEST 7] Testing an IR-mutating pass advances the generation and produces a real diff...")
    compiler, skill, ir = _compile_ir("franka_panda")
    pm = PassManager([_StripLastSafetyCheckPass()])
    trace = pm.run(ir, skill, compiler.robot_spec, OptimizationLevel.O1)

    assert trace.records[0].modified is True
    assert trace.records[0].ir_before is ir
    assert trace.records[0].ir_after is not ir
    assert trace.final_ir is not ir
    assert len(trace.final_ir.verification.safety_checks) == len(ir.verification.safety_checks) - 1

    diffs = diff_trace(trace)
    assert len(diffs) == 1
    name, d = diffs[0]
    assert name == "StripLastSafetyCheckPass"
    assert not d.is_empty()
    assert "verification.safety_checks" in d.field_changes
    print("  -> IR v1 -> v2 generation recorded, diff_trace() reports the real field change [PASSED]")


def test_compile_with_diagnostics_still_raises_rw102_first_for_temi_tighten():
    print("\n[TEST 8] Regression: PassManager wiring preserves RW102-first ordering...")
    compiler = SkillCompiler(target_robot="temi")
    with pytest.raises(SkillCompilationError) as exc_info:
        compiler.compile_with_diagnostics("Tighten the M8 bolt", verbose=False)
    assert exc_info.value.diagnostics[0].code == "RW102"
    print("  -> exc.diagnostics[0].code == 'RW102' still holds through the Pass Manager [PASSED]")


def test_compile_with_diagnostics_exposes_a_real_pipeline_trace():
    print("\n[TEST 9] Testing compile_with_diagnostics() attaches a real PipelineTrace...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    assert result.pipeline is not None
    assert [r.pass_name for r in result.pipeline.records] == [
        "RoboIRVerificationPass", "CapabilityPass", "SafetyPass",
    ]
    assert result.ir is result.pipeline.final_ir
    print("  -> result.pipeline has all 3 default passes; result.ir is the trace's final_ir [PASSED]")


def test_diff_ir_across_robots_shows_real_field_changes():
    print("\n[TEST 10] Testing diff_ir() reports real cross-robot differences...")
    panda_result = SkillCompiler(target_robot="franka_panda").compile_with_diagnostics(
        "Pick up the red cube", verbose=False
    )
    ur5e_result = SkillCompiler(target_robot="ur5e").compile_with_diagnostics(
        "Pick up the red cube", verbose=False
    )
    d = diff_ir(panda_result.ir, ur5e_result.ir)

    assert "execution.robot_id" in d.field_changes
    assert d.field_changes["execution.robot_id"] == (
        panda_result.ir.execution.robot_id, ur5e_result.ir.execution.robot_id,
    )
    panda_spec, ur5e_spec = get_robot_spec("franka_panda"), get_robot_spec("ur5e")
    if panda_spec.dof != ur5e_spec.dof:
        assert d.field_changes["execution.dof"] == (panda_spec.dof, ur5e_spec.dof)
    # skill_id is a random uuid per compile -- must not show up as noise by default.
    assert "skill_id" not in d.field_changes
    print(f"  -> execution.robot_id changed {panda_result.ir.execution.robot_id} -> {ur5e_result.ir.execution.robot_id}; skill_id ignored [PASSED]")


def test_optimization_level_plumbs_through_every_level_without_error():
    print("\n[TEST 11] Testing every OptimizationLevel value compiles without error (plumbing only)...")
    compiler = SkillCompiler(target_robot="franka_panda")
    for level in OptimizationLevel:
        result = compiler.compile_with_diagnostics(
            "Pick up the red cube", verbose=False, optimization_level=level
        )
        assert result.skill is not None
    print(f"  -> All {len(list(OptimizationLevel))} optimization levels compiled successfully [PASSED]")


if __name__ == "__main__":
    print("=== STARTING PASS MANAGER / IMMUTABLE IR / IR DIFF VERIFICATION ===")
    test_roboir_is_frozen()
    test_pass_manager_runs_passes_in_order_and_builds_trace()
    test_verification_pass_is_silent_on_a_real_build_ir_output()
    test_verification_pass_flags_a_deliberately_malformed_ir()
    test_capability_pass_matches_direct_function_call()
    test_safety_pass_matches_direct_function_call()
    test_ir_mutating_pass_produces_a_new_generation_and_a_real_diff()
    test_compile_with_diagnostics_still_raises_rw102_first_for_temi_tighten()
    test_compile_with_diagnostics_exposes_a_real_pipeline_trace()
    test_diff_ir_across_robots_shows_real_field_changes()
    test_optimization_level_plumbs_through_every_level_without_error()
    print("\n=== ALL PASS MANAGER / IMMUTABLE IR / IR DIFF TESTS PASSED SUCCESSFULLY ===")
