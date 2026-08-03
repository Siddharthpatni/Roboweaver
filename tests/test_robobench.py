"""
Verification suite for RoboBench (benchmark/robobench.py) -- item 11 of
docs/COMPILER_ROADMAP.md's v2 vision.
"""

from roboweaver.benchmark.robobench import _CANONICAL_INSTRUCTIONS, run_benchmark


def test_benchmark_produces_real_cells_for_a_small_robot_subset():
    print("\n[TEST 1] Testing run_benchmark() produces a real cell per (category, robot) pair...")
    robot_ids = ["franka_panda", "ur5e"]
    report = run_benchmark(robot_ids=robot_ids)

    expected_cells = len(_CANONICAL_INSTRUCTIONS) * len(robot_ids)
    assert len(report.cells) == expected_cells

    for cell in report.cells:
        assert cell.robot_id in robot_ids
        assert cell.category in _CANONICAL_INSTRUCTIONS
        assert cell.compile_time_s >= 0  # real, non-placeholder timing (can be 0.0 on a fast cache hit)
        assert cell.instruction == _CANONICAL_INSTRUCTIONS[cell.category]
    print(f"  -> {len(report.cells)} real cells ({len(_CANONICAL_INSTRUCTIONS)} categories x {len(robot_ids)} robots) [PASSED]")


def test_benchmark_records_a_real_failure_when_a_robot_genuinely_cant_compile():
    print("\n[TEST 2] Testing run_benchmark() records a real failure cell, not a silent skip...")
    # temi has no force/torque sensor -- TIGHTEN_BOLT genuinely fails to compile
    # for it (RW102), same real gap test_ir.py's Compiler Debugger tests exercise.
    report = run_benchmark(robot_ids=["temi"])
    tighten_cell = next(c for c in report.cells if c.category == "TIGHTEN_BOLT")
    assert tighten_cell.success is False
    assert tighten_cell.error_count >= 1
    assert tighten_cell.failure_reason is not None
    print(f"  -> real failure recorded for temi/TIGHTEN_BOLT: {tighten_cell.failure_reason} [PASSED]")


def test_report_to_dict_scope_is_honest_about_what_was_measured():
    print("\n[TEST 3] Testing the report's scope string honestly describes compile-time-only measurement...")
    report = run_benchmark(robot_ids=["franka_panda"])
    data = report.to_dict()
    assert "compile-time" in data["scope"]
    assert "simulator" in data["scope"]
    assert data["total_cells"] == len(_CANONICAL_INSTRUCTIONS)
    print(f"  -> scope: {data['scope']} [PASSED]")


if __name__ == "__main__":
    print("=== STARTING ROBOBENCH (ITEM 11) VERIFICATION ===")
    test_benchmark_produces_real_cells_for_a_small_robot_subset()
    test_benchmark_records_a_real_failure_when_a_robot_genuinely_cant_compile()
    test_report_to_dict_scope_is_honest_about_what_was_measured()
    print("\n=== ALL ROBOBENCH TESTS PASSED SUCCESSFULLY ===")
