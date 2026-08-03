"""
Verification suite for the self-learning compiler mechanism (optimize/learning.py)
-- item 12 of docs/COMPILER_ROADMAP.md's v2 vision.
"""

import tempfile

from roboweaver.optimize.learning import suggest_parameter_adjustments
from roboweaver.runtime.memory import ExecutionMemoryStore


def test_returns_none_below_min_samples():
    print("\n[TEST 1] Testing suggest_parameter_adjustments() returns None with too little real history...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        for _ in range(3):  # fewer than the default min_samples=5
            memory.record({"task": {"action": "PICK", "robot_id": "r1", "object_name": "x"}, "execution": {"success": True}})
        result = suggest_parameter_adjustments("PICK", "r1", memory)
        assert result is None
    print("  -> None returned -- this repo's honest default with zero/sparse accumulated history [PASSED]")


def test_returns_none_when_real_history_shows_no_problem():
    print("\n[TEST 2] Testing suggest_parameter_adjustments() returns None when real history is all healthy...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        for _ in range(10):
            memory.record({
                "task": {"action": "PICK", "robot_id": "r1", "object_name": "x"},
                "execution": {"success": True, "joint_limits_respected": True, "recovery_attempts": []},
            })
        result = suggest_parameter_adjustments("PICK", "r1", memory)
        assert result is None
    print("  -> None returned -- no fabricated suggestion when nothing real is wrong [PASSED]")


def test_returns_a_real_suggestion_from_a_real_low_success_pattern():
    print("\n[TEST 3] Testing suggest_parameter_adjustments() surfaces a real low-success-rate pattern...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        for i in range(10):
            memory.record({
                "task": {"action": "PICK", "robot_id": "r1", "object_name": "x"},
                "execution": {"success": (i < 3), "joint_limits_respected": True, "recovery_attempts": []},
            })
        result = suggest_parameter_adjustments("PICK", "r1", memory)
        assert result is not None
        assert any("3/10" in s for s in result)
    print(f"  -> real suggestion from real 3/10 success rate: {result[0]} [PASSED]")


def test_returns_a_real_suggestion_from_frequent_recovery():
    print("\n[TEST 4] Testing suggest_parameter_adjustments() surfaces a real frequent-recovery pattern...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        for i in range(10):
            attempts = [{"failure_mode": "GRASP_FAILED", "action": "WIDEN_APPROACH", "reason": "x"}] if i < 5 else []
            memory.record({
                "task": {"action": "PICK", "robot_id": "r1", "object_name": "x"},
                "execution": {"success": True, "joint_limits_respected": True, "recovery_attempts": attempts},
            })
        result = suggest_parameter_adjustments("PICK", "r1", memory)
        assert result is not None
        assert any("WIDEN_APPROACH" in s for s in result)
    print(f"  -> real suggestion from WIDEN_APPROACH needed in 5/10 real runs: {result[0]} [PASSED]")


if __name__ == "__main__":
    print("=== STARTING SELF-LEARNING MECHANISM (ITEM 12) VERIFICATION ===")
    test_returns_none_below_min_samples()
    test_returns_none_when_real_history_shows_no_problem()
    test_returns_a_real_suggestion_from_a_real_low_success_pattern()
    test_returns_a_real_suggestion_from_frequent_recovery()
    print("\n=== ALL SELF-LEARNING MECHANISM TESTS PASSED SUCCESSFULLY ===")
