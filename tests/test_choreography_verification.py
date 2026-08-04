"""
Verification suite for fleet/choreography_verification.py -- static analysis over
WorkcellSchedule's real multi-robot DAG (docs/COMPILER_ROADMAP.md Phase 3).
"""

import pytest

from roboweaver.fleet.choreographer import WorkcellSchedule, MultiRobotChoreographer
from roboweaver.fleet.choreography_verification import check_choreography
from roboweaver.ir import SkillCompilationError


def test_well_formed_schedule_is_clean():
    print("\n[TEST 1] Testing a well-formed acyclic schedule produces no diagnostics...")
    schedule = WorkcellSchedule(workcell_name="clean")
    schedule.add_step("s1", "temi", "Navigate to shelf")
    schedule.add_step("s2", "pepper", "Receive tray", depends_on=["s1"])
    schedule.add_step("s3", "franka_panda", "Place tray on bench", depends_on=["s2"])

    diagnostics = check_choreography(schedule)
    assert diagnostics == []
    print("  -> No diagnostics for a real, well-formed 3-step DAG [PASSED]")


def test_cyclic_dependency_detected():
    print("\n[TEST 2] Testing RW601 catches a real cyclic dependency...")
    schedule = WorkcellSchedule(workcell_name="cyclic")
    schedule.add_step("a", "temi", "Step A", depends_on=["b"])
    schedule.add_step("b", "pepper", "Step B", depends_on=["a"])

    diagnostics = check_choreography(schedule)
    codes = [d.code for d in diagnostics]
    assert "RW601" in codes
    rw601 = next(d for d in diagnostics if d.code == "RW601")
    assert rw601.severity == "error"
    assert "a" in rw601.reason and "b" in rw601.reason
    print(f"  -> RW601 raised, reason cites both cyclic steps: {rw601.reason} [PASSED]")


def test_resource_conflict_detected_within_a_tier():
    print("\n[TEST 3] Testing RW602 catches the same robot double-booked in one execution tier...")
    schedule = WorkcellSchedule(workcell_name="conflict")
    # Neither step depends on the other -- both land in tier 0 -- but both target
    # the same physical robot, which cannot execute two steps at once.
    schedule.add_step("s1", "franka_panda", "Pick part A")
    schedule.add_step("s2", "franka_panda", "Pick part B")

    diagnostics = check_choreography(schedule)
    codes = [d.code for d in diagnostics]
    assert "RW602" in codes
    rw602 = next(d for d in diagnostics if d.code == "RW602")
    assert rw602.severity == "error"
    assert "franka_panda" in rw602.message
    print(f"  -> RW602 raised for concurrent same-robot steps: {rw602.message} [PASSED]")


def test_resource_conflict_not_raised_when_dependency_orders_them():
    print("\n[TEST 4] Testing RW602 does NOT fire when a depends_on edge orders same-robot steps...")
    schedule = WorkcellSchedule(workcell_name="no_conflict")
    schedule.add_step("s1", "franka_panda", "Pick part A")
    schedule.add_step("s2", "franka_panda", "Pick part B", depends_on=["s1"])

    diagnostics = check_choreography(schedule)
    assert diagnostics == []
    print("  -> No RW602 when the same robot's two steps are properly ordered [PASSED]")


def test_dangling_depends_on_detected():
    print("\n[TEST 5] Testing RW605 catches a depends_on reference to a nonexistent step...")
    schedule = WorkcellSchedule(workcell_name="dangling")
    schedule.add_step("s1", "temi", "Step 1", depends_on=["does_not_exist"])

    diagnostics = check_choreography(schedule)
    codes = [d.code for d in diagnostics]
    assert codes == ["RW605"]
    assert diagnostics[0].severity == "error"
    assert "does_not_exist" in diagnostics[0].reason
    print(f"  -> RW605 raised, cycle/tier analysis correctly skipped: {diagnostics[0].reason} [PASSED]")


def test_handover_to_unknown_robot_detected():
    print("\n[TEST 7] Testing RW603 catches a handover_target that names no real robot in the schedule...")
    schedule = WorkcellSchedule(workcell_name="bad_handover")
    schedule.add_step("s1", "temi", "Transport tray", handover_target="pepper")
    # No "pepper" step anywhere in this schedule -- a real, checkable bug.

    diagnostics = check_choreography(schedule)
    codes = [d.code for d in diagnostics]
    assert "RW603" in codes
    rw603 = next(d for d in diagnostics if d.code == "RW603")
    assert rw603.severity == "error"
    assert "pepper" in rw603.reason
    print(f"  -> RW603 raised for a handover to a robot not in the workcell: {rw603.reason} [PASSED]")


def test_handover_with_no_downstream_receiving_step_detected():
    print("\n[TEST 8] Testing RW604 catches a real handover with no downstream continuation...")
    schedule = WorkcellSchedule(workcell_name="stranded_handover")
    schedule.add_step("s1", "temi", "Transport tray", handover_target="pepper")
    schedule.add_step("s2", "pepper", "Unrelated pepper task")  # exists, but doesn't depend on s1

    diagnostics = check_choreography(schedule)
    codes = [d.code for d in diagnostics]
    assert "RW604" in codes
    rw604 = next(d for d in diagnostics if d.code == "RW604")
    assert rw604.severity == "warning"
    print(f"  -> RW604 raised: {rw604.message} [PASSED]")


def test_handover_with_real_downstream_receiving_step_is_clean():
    print("\n[TEST 9] Testing a real, properly-ordered handover produces no RW603/RW604...")
    schedule = WorkcellSchedule(workcell_name="real_handover")
    schedule.add_step("s1", "temi", "Transport tray", handover_target="pepper")
    schedule.add_step("s2", "pepper", "Receive tray from temi", depends_on=["s1"])

    diagnostics = check_choreography(schedule)
    assert diagnostics == []
    print("  -> No RW603/RW604 when the receiving robot's step really depends on the handoff [PASSED]")


def test_existing_pepper_to_pepper_fixture_is_unaffected():
    print("\n[TEST 10] Regression: the same-robot handover_target fixture from "
          "test_multi_robot_choreography.py stays clean under the new real validation...")
    # Mirrors tests/test_multi_robot_choreography.py's real fixture: step 3
    # (robot=pepper) declares handover_target="pepper" (itself), and step 4
    # (also pepper) depends on step 3 -- so a downstream pepper step exists,
    # even though the "handoff" is self-referential.
    schedule = WorkcellSchedule(workcell_name="pepper_fixture")
    schedule.add_step("s1", "temi", "Navigate")
    schedule.add_step("s2", "temi", "Transport", depends_on=["s1"])
    schedule.add_step("s3", "pepper", "Receive", depends_on=["s2"], handover_target="pepper")
    schedule.add_step("s4", "pepper", "Place on bench", depends_on=["s3"])

    diagnostics = check_choreography(schedule)
    assert [d.code for d in diagnostics if d.code in ("RW603", "RW604")] == []
    print("  -> Real fixture stays clean: pepper is a real robot here, and s4 (pepper) depends on s3 [PASSED]")


def test_compile_workcell_raises_on_cyclic_schedule():
    print("\n[TEST 6] Testing MultiRobotChoreographer.compile_workcell() refuses a cyclic schedule...")
    choreographer = MultiRobotChoreographer(workcell_name="cyclic_integration")
    choreographer.add_robot_task("a", "temi", "Step A", depends_on=["b"])
    choreographer.add_robot_task("b", "pepper", "Step B", depends_on=["a"])

    with pytest.raises(SkillCompilationError) as exc_info:
        choreographer.compile_workcell(verbose=False)
    assert exc_info.value.diagnostics[0].code == "RW601"
    print("  -> compile_workcell() raised SkillCompilationError with RW601 before compiling any step [PASSED]")


if __name__ == "__main__":
    print("=== STARTING CHOREOGRAPHY STATIC ANALYSIS (PHASE 3) VERIFICATION ===")
    test_well_formed_schedule_is_clean()
    test_cyclic_dependency_detected()
    test_resource_conflict_detected_within_a_tier()
    test_resource_conflict_not_raised_when_dependency_orders_them()
    test_dangling_depends_on_detected()
    test_handover_to_unknown_robot_detected()
    test_handover_with_no_downstream_receiving_step_detected()
    test_handover_with_real_downstream_receiving_step_is_clean()
    test_existing_pepper_to_pepper_fixture_is_unaffected()
    test_compile_workcell_raises_on_cyclic_schedule()
    print("\n=== ALL CHOREOGRAPHY STATIC ANALYSIS TESTS PASSED SUCCESSFULLY ===")
