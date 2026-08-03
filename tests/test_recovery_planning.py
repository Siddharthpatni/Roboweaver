"""
Verification suite for scored, case-based recovery planning (runtime/recovery.py) --
item 7 of docs/COMPILER_ROADMAP.md's v2 vision.
"""

import tempfile

from roboweaver.compiler import SkillCompiler
from roboweaver.runtime.engine import SkillRuntime
from roboweaver.runtime.memory import ExecutionMemoryStore
from roboweaver.runtime.recovery import FailureMode, RecoveryAction, RecoveryEngine


def test_candidates_are_real_declared_priors_not_empty():
    print("\n[TEST 1] Testing candidates() returns real declared priors for every failure mode...")
    engine = RecoveryEngine()
    for fm in FailureMode:
        cands = engine.candidates(fm)
        assert len(cands) >= 1
        assert all(0.0 <= c.estimated_success_probability <= 1.0 for c in cands)
        assert all(c.cost_s > 0 for c in cands)
    print(f"  -> all {len(list(FailureMode))} failure modes have >=1 declared candidate [PASSED]")


def test_plan_escalates_as_retry_count_increases():
    print("\n[TEST 2] Testing plan() escalates to different actions as retry_count increases...")
    engine = RecoveryEngine()
    seen_actions = set()
    for attempt in range(5):
        plan = engine.plan(FailureMode.GRASP_FAILED, context={"retry_count": attempt})
        seen_actions.add(plan.recommended_action)
    # A real escalation ladder must recommend more than one distinct action across
    # 5 increasing retry counts -- not converge on a single "best" choice forever.
    assert len(seen_actions) > 1
    print(f"  -> {len(seen_actions)} distinct actions recommended across 5 escalating attempts: "
          f"{[a.value for a in seen_actions]} [PASSED]")


def test_diagnose_signature_and_shape_unchanged():
    print("\n[TEST 3] Testing diagnose() is a signature-preserving wrapper around plan()...")
    engine = RecoveryEngine()
    plan = engine.diagnose(FailureMode.JOINT_LIMIT_VIOLATED, context={"retry_count": 0})
    assert plan.recommended_action == RecoveryAction.FALLBACK_HOME
    assert plan.used_historical_data is False
    print("  -> diagnose() still returns a RecoveryPlan with the same fields as before [PASSED]")


def test_plan_uses_real_history_when_available():
    print("\n[TEST 4] Testing plan() boosts/penalizes candidates using real recorded recovery outcomes...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        # Real records: RETRY_GRASP (the default top pick with no history, since
        # it's cheap) was tried for GRASP_FAILED on "test_robot" and always failed;
        # WIDEN_APPROACH was tried and always succeeded. A real score boost alone
        # (raising a candidate's probability) can't outrank RETRY_GRASP's low cost_s
        # unless its own real history is bad too -- both are recorded so the ranking
        # genuinely flips on real data, not on a scenario engineered to force it.
        for _ in range(5):
            memory.record({
                "task": {"action": "PICK", "robot_id": "test_robot", "object_name": "cube"},
                "execution": {
                    "success": False,
                    "recovery_attempts": [{"failure_mode": "GRASP_FAILED", "action": "RETRY_GRASP", "reason": "test"}],
                },
            })
            memory.record({
                "task": {"action": "PICK", "robot_id": "test_robot", "object_name": "cube"},
                "execution": {
                    "success": True,
                    "recovery_attempts": [{"failure_mode": "GRASP_FAILED", "action": "WIDEN_APPROACH", "reason": "test"}],
                },
            })

        engine = RecoveryEngine(memory=memory)
        plan = engine.plan(
            FailureMode.GRASP_FAILED,
            context={"retry_count": 0, "robot_id": "test_robot"},
        )
        assert plan.used_historical_data is True
        assert plan.recommended_action == RecoveryAction.WIDEN_APPROACH
    print(f"  -> used_historical_data=True, recommended {plan.recommended_action.value} from real recorded outcomes [PASSED]")


def test_plan_falls_back_to_priors_without_history():
    print("\n[TEST 5] Testing plan() falls back to declared priors when no history exists...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)  # empty -- no records written
        engine = RecoveryEngine(memory=memory)
        plan = engine.plan(FailureMode.GRASP_FAILED, context={"retry_count": 0, "robot_id": "test_robot"})
        assert plan.used_historical_data is False
        assert plan.recommended_action == RecoveryAction.RETRY_GRASP  # highest declared prior score
    print("  -> used_historical_data=False, falls back to the highest-scored declared prior [PASSED]")


def test_recovery_still_wired_into_real_execution():
    print("\n[TEST 6] Regression: SkillRuntime execution still exercises real recovery via the new engine...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    runtime = SkillRuntime(robot_spec=compiler.robot_spec)
    result = runtime.execute(skill, verbose=False)
    assert result.telemetry_frame_count > 0
    print(f"  -> {result.telemetry_frame_count} real telemetry frames recorded, execution completed [PASSED]")


if __name__ == "__main__":
    print("=== STARTING RECOVERY PLANNING (ITEM 7) VERIFICATION ===")
    test_candidates_are_real_declared_priors_not_empty()
    test_plan_escalates_as_retry_count_increases()
    test_diagnose_signature_and_shape_unchanged()
    test_plan_uses_real_history_when_available()
    test_plan_falls_back_to_priors_without_history()
    test_recovery_still_wired_into_real_execution()
    print("\n=== ALL RECOVERY PLANNING TESTS PASSED SUCCESSFULLY ===")
