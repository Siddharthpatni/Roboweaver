"""Semantic Cartesian lowering inputs and pose-provenance verification."""

from roboweaver.compiler import SkillCompiler
from roboweaver.types import TaskType


def _targets(portable):
    return [
        task.params["target_pose_m"]
        for task in portable.task_graph.tasks
        if task.type is TaskType.MOVE_TO
    ]


def test_portable_cartesian_inputs_do_not_depend_on_selected_robot():
    source = "Pick up the red cube at x=0.30 y=0.02 z=0.12"
    franka = SkillCompiler("franka_panda").compile_portable(source, verbose=False)
    ur5e = SkillCompiler("ur5e").compile_portable(source, verbose=False)
    assert _targets(franka) == _targets(ur5e)


def test_actions_with_equal_motion_counts_no_longer_share_one_fixed_path():
    compiler = SkillCompiler("franka_panda")
    weld = compiler.compile_portable("Weld the steel bracket seam", verbose=False)
    inspect = compiler.compile_portable("Inspect the machine panel", verbose=False)
    assert len(_targets(weld)) == len(_targets(inspect))
    assert _targets(weld) != _targets(inspect)


def test_user_cartesian_pose_is_preserved_and_removes_missing_pose_warning():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the red cube at x=0.30 y=0.02 z=0.12",
        verbose=False,
    )
    assert result.ir.objects[0].pose_source == "user_specified"
    assert "RW201" not in {diagnostic.code for diagnostic in result.diagnostics}
    assert result.ir.program is not None
    move_tasks = [task for task in result.ir.program.tasks if task.type == "MOVE_TO"]
    assert all(task.parameters["pose_source"] == "user_specified" for task in move_tasks)
    assert all(task.type != "PERCEIVE" for task in result.ir.program.tasks)
    assert "Locate target red_cube" not in result.skill.behavior_tree.pretty()


def test_one_pose_does_not_erase_a_richer_perception_contract():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Sort the item at x=0.30 y=0.02 z=0.12",
        verbose=False,
    )
    assert "RW201" in {diagnostic.code for diagnostic in result.diagnostics}
    assert result.ir.program is not None
    assert any(task.type == "PERCEIVE" for task in result.ir.program.tasks)


def test_partial_cartesian_pose_is_not_misrepresented_as_measured_input():
    portable = SkillCompiler("franka_panda").compile_portable(
        "Pick up the red cube at x=0.30 y=0.02",
        verbose=False,
    )
    assert any("partial Cartesian pose" in warning for warning in portable.intent.parse_warnings)
    assert all(
        task.params.get("pose_source") == "assumed_default"
        for task in portable.task_graph.tasks
        if task.type is TaskType.MOVE_TO
    )
