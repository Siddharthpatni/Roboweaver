"""
Verification suite for bounded formal verification (optimize/formal.py) -- item 10
of docs/COMPILER_ROADMAP.md's v2 vision.
"""

import dataclasses

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.ir import SkillCompilationError
from roboweaver.optimize.formal import check_forbidden_zone_violations


def _real_skill(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler.compile("Pick up the red cube", verbose=False)


def test_no_declared_zone_returns_empty_honestly():
    print("\n[TEST 1] Testing check_forbidden_zone_violations() returns [] when nothing is declared...")
    skill = _real_skill()
    assert check_forbidden_zone_violations(skill, None) == []
    assert check_forbidden_zone_violations(skill, {}) == []
    print("  -> [] returned honestly -- no fabricated violation or proof without a declared zone [PASSED]")


def test_real_violation_detected_against_a_declared_zone():
    print("\n[TEST 2] Testing a real declared forbidden zone that the real trajectory actually enters is caught...")
    skill = _real_skill()
    # Pick a real joint index and derive a forbidden range from the skill's own
    # real waypoint data, so the "violation" is genuinely computed, not asserted.
    seg = next(iter(skill.motion_plan.trajectories.values()))
    joint_idx = 0
    sample_value = seg.waypoints[len(seg.waypoints) // 2][joint_idx]
    forbidden = {joint_idx: (sample_value - 0.01, sample_value + 0.01)}

    diagnostics = check_forbidden_zone_violations(skill, forbidden)
    assert len(diagnostics) >= 1
    assert diagnostics[0].code == "RW507"
    assert diagnostics[0].severity == "error"
    print(f"  -> RW507 raised for a real waypoint value inside the declared forbidden range: {diagnostics[0].reason} [PASSED]")


def test_declared_zone_the_trajectory_never_enters_is_clean():
    print("\n[TEST 3] Testing a declared forbidden zone the real trajectory never enters produces no diagnostics...")
    skill = _real_skill()
    # A range far outside any real joint value this compiled skill ever produces.
    forbidden = {0: (100.0, 200.0)}
    diagnostics = check_forbidden_zone_violations(skill, forbidden)
    assert diagnostics == []
    print("  -> No RW507 for a forbidden zone the real trajectory never enters [PASSED]")


@pytest.mark.parametrize(
    "declaration",
    [
        {-1: (-0.1, 0.1)},
        {0: (1.0, -1.0)},
        {0: (float("nan"), 1.0)},
        {0: (False, 1.0)},
        {999: (-0.1, 0.1)},
    ],
)
def test_invalid_forbidden_zone_declarations_fail_closed(declaration):
    diagnostics = check_forbidden_zone_violations(_real_skill(), declaration)
    assert diagnostics
    assert diagnostics[0].code == "RW508"
    assert diagnostics[0].severity == "error"


def test_compiler_pipeline_blocks_a_declared_sampled_zone_violation():
    source = "Pick up the red cube at x=0.30 y=0.02 z=0.12"
    baseline = SkillCompiler("franka_panda").compile(source, verbose=False)
    segment = next(iter(baseline.motion_plan.trajectories.values()))
    sample = segment.waypoints[len(segment.waypoints) // 2][0]
    guarded_spec = dataclasses.replace(
        get_robot_spec("franka_panda"),
        forbidden_joint_ranges={0: (sample - 0.001, sample + 0.001)},
    )

    with pytest.raises(SkillCompilationError) as exc_info:
        SkillCompiler(guarded_spec).compile_with_diagnostics(source, verbose=False)

    assert any(diagnostic.code == "RW507" for diagnostic in exc_info.value.diagnostics)


if __name__ == "__main__":
    print("=== STARTING BOUNDED FORMAL VERIFICATION (ITEM 10) VERIFICATION ===")
    test_no_declared_zone_returns_empty_honestly()
    test_real_violation_detected_against_a_declared_zone()
    test_declared_zone_the_trajectory_never_enters_is_clean()
    print("\n=== ALL FORMAL VERIFICATION TESTS PASSED SUCCESSFULLY ===")
