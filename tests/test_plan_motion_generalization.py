"""
Verification suite for the generalized compiler.py::_plan_motion (gap-fix batch,
item 1a): one real, IK-solved trajectory segment per actual MOVE_TO task, closing
RW502 (optimize/passes.py) for every skill category -- not just pick-and-place.
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import check_safety, build_ir
from roboweaver.optimize import motion_cache
from roboweaver.types import TaskType

# One real instruction per NL-reachable category (matches benchmark/robobench.py's
# canonical set), pre-fix.
_INSTRUCTIONS = {
    "PICK_AND_PLACE": "Pick up the red cube",
    "TIGHTEN_BOLT": "Tighten the M8 bolt",
    "OPEN_DOOR": "Open the door",
    "TOOL_EXCHANGE": "Exchange the tool",
    "INSPECT_SURFACE": "Inspect the surface of the panel",
    "WELD_SEAM": "Weld the seam",
    "PEGGING": "Insert the peg into the alignment hole",
    "POURING_LIQUID": "Pour the liquid into the beaker",
    "PACKAGING": "Pack the item into the carton",
    "CNC_LOADING": "Load the workpiece into the CNC chuck",
    "SURGERY_ASSIST": "Assist with the surgical instrument",
    "SORTING": "Sort the item into the correct bin",
    "CLEANING": "Clean the work surface",
}


def test_every_move_to_task_gets_a_real_trajectory_entry():
    print("\n[TEST 1] Testing every MOVE_TO task across every reachable category gets a real motion_plan entry...")
    for category, instruction in _INSTRUCTIONS.items():
        compiler = SkillCompiler(target_robot="franka_panda")
        skill = compiler.compile(instruction, verbose=False)
        move_to_tasks = [t for t in skill.task_graph.tasks if t.type is TaskType.MOVE_TO]
        assert move_to_tasks, f"{category} has no MOVE_TO tasks at all"
        for task in move_to_tasks:
            assert task.description in skill.motion_plan.trajectories, (
                f"{category}: MOVE_TO task {task.description!r} has no trajectory entry"
            )
            assert task.description in skill.motion_plan.ik_results
    print(f"  -> all {len(_INSTRUCTIONS)} reachable categories: every MOVE_TO task has real motion data [PASSED]")


def test_no_rw502_across_every_reachable_category():
    print("\n[TEST 2] Testing RW502 no longer fires for any reachable category...")
    for category, instruction in _INSTRUCTIONS.items():
        compiler = SkillCompiler(target_robot="franka_panda")
        result = compiler.compile_with_diagnostics(instruction, verbose=False)
        rw502 = [d for d in result.diagnostics if d.code == "RW502"]
        assert rw502 == [], f"{category} still has RW502: {rw502}"
    print(f"  -> 0 RW502 diagnostics across all {len(_INSTRUCTIONS)} reachable categories [PASSED]")


def test_trajectories_are_real_and_safety_verified():
    print("\n[TEST 3] Testing generalized trajectories pass the real safety pass (RW304 velocity limits)...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Weld the seam", verbose=False)
    ir = build_ir(skill.intent, compiler.robot_spec, raw_instruction="test")
    diagnostics = check_safety(skill, ir, compiler.robot_spec)
    velocity_violations = [d for d in diagnostics if d.code == "RW304"]
    assert velocity_violations == []
    # Real, distinct IK-solved joint configurations per task -- not placeholders.
    ik_results = skill.motion_plan.ik_results
    assert all(ik.success for ik in ik_results.values())
    configs = [tuple(ik.joint_angles) for ik in ik_results.values()]
    assert len(set(configs)) == len(configs), "expected distinct configs per MOVE_TO task"
    print(f"  -> {len(ik_results)} distinct, safety-verified IK configs for WELD_SEAM [PASSED]")


def test_motion_cache_keyed_by_robot_and_n_targets():
    print("\n[TEST 4] Testing the motion cache is correctly keyed by (robot, n_targets)...")
    from roboweaver.hardware import get_robot_spec
    motion_cache.clear_cache()
    spec = get_robot_spec("ur5e")

    primitives_3, hit_3 = motion_cache.compute_motion_primitives(spec, 3)
    primitives_2, hit_2 = motion_cache.compute_motion_primitives(spec, 2)
    primitives_3_again, hit_3_again = motion_cache.compute_motion_primitives(spec, 3)

    assert hit_3 is False
    assert hit_2 is False  # different n_targets -- a real cache miss, not reused
    assert hit_3_again is True
    assert primitives_3 is primitives_3_again
    assert len(primitives_3.ik_solutions) == 3
    assert len(primitives_2.ik_solutions) == 2
    print("  -> (robot, n_targets) cache keys don't collide across different segment counts [PASSED]")


if __name__ == "__main__":
    print("=== STARTING _plan_motion GENERALIZATION (GAP-FIX ITEM 1a) VERIFICATION ===")
    test_every_move_to_task_gets_a_real_trajectory_entry()
    test_no_rw502_across_every_reachable_category()
    test_trajectories_are_real_and_safety_verified()
    test_motion_cache_keyed_by_robot_and_n_targets()
    print("\n=== ALL _plan_motion GENERALIZATION TESTS PASSED SUCCESSFULLY ===")
