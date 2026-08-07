"""Proof that one semantic program is lowered independently across targets."""

import dataclasses

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec


def test_compile_targets_parses_once_and_reuses_one_portable_program():
    matrix = SkillCompiler.compile_targets(
        "Pick up the red cube",
        ["franka_panda", "ur5e", "kuka_iiwa"],
    )

    assert matrix.failures == {}
    assert set(matrix.results) == {"franka_panda", "ur5e", "kuka_iiwa"}
    assert len(matrix.source_digest) == 64
    for result in matrix.results.values():
        assert result.portable is matrix.portable
        assert result.ir.program is not None
        assert result.ir.lowering is not None

    programs = [result.ir.program.to_dict() for result in matrix.results.values()]
    assert programs[1:] == programs[:-1]

    lowerings = [result.ir.lowering for result in matrix.results.values()]
    assert {lowering.robot_id for lowering in lowerings} == {
        "franka_panda", "ur5e", "kuka_iiwa",
    }
    assert {len(lowering.joint_names) for lowering in lowerings} == {6, 7}


def test_portable_source_digest_is_independent_of_target_order():
    first = SkillCompiler.compile_targets("Pick up the red cube", ["franka_panda", "ur5e"])
    second = SkillCompiler.compile_targets("Pick up the red cube", ["ur5e", "franka_panda"])
    assert first.source_digest == second.source_digest


def test_skill_identity_is_reproducible_and_shared_across_targets():
    instruction = "Pick up the red cube x=0.42 y=0.10 z=0.25"
    first = SkillCompiler.compile_targets(
        instruction, ["franka_panda", "ur5e"], verbose=False
    )
    second = SkillCompiler.compile_targets(
        instruction, ["ur5e", "franka_panda"], verbose=False
    )

    first_ids = {result.ir.skill_id for result in first.results.values()}
    second_ids = {result.ir.skill_id for result in second.results.values()}
    assert len(first_ids) == 1
    assert first_ids == second_ids


def test_target_failure_does_not_invalidate_other_lowerings():
    matrix = SkillCompiler.compile_targets(
        "Tighten the M8 bolt",
        ["franka_panda", "temi"],
    )
    assert "franka_panda" in matrix.results
    assert "temi" in matrix.failures
    assert any(diagnostic.severity == "error" for diagnostic in matrix.failures["temi"])


def test_unregistered_valid_robot_spec_uses_the_same_universal_pipeline():
    custom = dataclasses.replace(
        get_robot_spec("generic_6dof"),
        id="acme_custom_6axis",
        name="ACME Custom Six Axis",
        manufacturer="ACME Integration",
    )
    result = SkillCompiler(custom).compile_with_diagnostics(
        "Pick up the red cube at x=0.30 y=0.02 z=0.12",
        verbose=False,
    )

    assert result.ir.execution.robot_id == "acme_custom_6axis"
    assert result.ir.lowering is not None
    assert result.ir.lowering.robot_id == "acme_custom_6axis"
    assert result.ir.lowering.joint_names == tuple(joint.name for joint in custom.joints)


def test_malformed_unregistered_robot_spec_fails_at_the_compiler_boundary():
    malformed = dataclasses.replace(
        get_robot_spec("generic_6dof"),
        id="broken_custom",
        links=[],
    )
    with pytest.raises(ValueError, match="invalid RobotSpec 'broken_custom'"):
        SkillCompiler(malformed)
