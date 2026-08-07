"""Target dialect legality and embodiment-specific lowering evidence."""

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import SkillCompilationError


@pytest.mark.parametrize(
    ("robot_id", "instruction", "model", "solver"),
    [
        ("franka_panda", "Pick up the cube", "serial_arm", "damped_pseudoinverse_ik"),
        ("temi", "Navigate to dock x=0.8 y=0 z=0.1", "holonomic_base", "holonomic_se2"),
        ("turtlebot4", "Navigate to dock x=0.8 y=0 z=0.1", "differential_drive", "differential_drive_se2"),
        ("shadow_hand", "Pick up the cube", "multi_finger_hand", "multi_finger_posture"),
    ],
)
def test_motion_models_use_dedicated_lowerers(robot_id, instruction, model, solver):
    result = SkillCompiler(robot_id).compile_with_diagnostics(instruction, verbose=False)
    assert result.ir.lowering.motion_model == model
    assert result.ir.execution.planner == model
    assert {item.solver for item in result.ir.lowering.ik_solutions} == {solver}


def test_branched_humanoid_lowers_only_one_declared_branch_into_full_state():
    skill = SkillCompiler("pepper").compile("Pick up the cube", verbose=False)
    assert skill.motion_plan.lowerer == "branched_humanoid"
    assert all(item.solver.startswith("branch_ik:right_arm") for item in skill.motion_plan.ik_results.values())
    assert all(len(item.joint_angles) == 17 for item in skill.motion_plan.ik_results.values())


def test_illegal_mobile_manipulation_fails_at_conversion_target():
    with pytest.raises(SkillCompilationError) as caught:
        SkillCompiler("temi").compile_with_diagnostics("Pick up the cube", verbose=False)
    assert caught.value.diagnostics[0].code == "RW601"
