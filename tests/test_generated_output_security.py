"""Regression tests for untrusted names crossing code and filesystem boundaries."""


import pytest

from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.codegen.ros2_gen import generate_ros2_package
from roboweaver.codegen.urscript_gen import generate_urscript
from roboweaver.compiler import SkillCompiler
from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.ir.builder import build_ir
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata
from roboweaver.registry.repository import SkillRepository


def _skill_with_hostile_names():
    result = SkillCompiler("ur5e").compile_with_diagnostics(
        "Pick up the red cube",
        verbose=False,
    )
    result.skill.intent.object_name = "../../escape\nend\ndef injected():"
    result.skill.task_graph.tasks[0].description = "observe\nend\ntextmsg('injected')"
    result.ir = build_ir(
        result.skill.intent,
        get_robot_spec("ur5e"),
        "hostile input",
        result.skill,
    )
    return result


def test_generated_sources_sanitize_names_and_remain_inside_output_directory(tmp_path):
    result = _skill_with_hostile_names()
    package_dir = generate_ros2_package(result.ir, tmp_path)
    assert package_dir.parent == tmp_path
    assert package_dir.name == "roboweaver_pick_escape_end_def_injected"

    script_path = generate_urscript(
        result.ir,
        get_robot_spec("ur5e"),
        tmp_path / "skill.script",
    )
    script = script_path.read_text(encoding="utf-8")
    assert "\nend\ndef injected" not in script
    assert "\nend\ntextmsg" not in script
    assert "def roboweaver_pick_escape_end_def_injected():" in script

    xml = export_groot2_xml(result.skill)
    assert 'ID="pick_escape_end_def_injected_tree"' in xml

    ir = build_ir(result.skill.intent, get_robot_spec("ur5e"), "hostile input", result.skill)
    assert ".." not in ir.skill_id
    assert "/" not in ir.skill_id
    assert "\n" not in ir.skill_id


def test_persisted_package_ids_reject_path_traversal(tmp_path):
    result = _skill_with_hostile_names()
    metadata = SkillPackageMetadata(
        id="../../outside",
        name="Hostile",
        version="1.0.0",
        description="test",
        action="PICK",
        target_object="object",
    )
    package = SkillPackage(metadata, result.skill)
    repository = SkillRepository(tmp_path / "registry")

    with pytest.raises(ValueError, match="skill package id"):
        repository.register(package)
    with pytest.raises(ValueError, match="skill package id"):
        package.export_archive(tmp_path / "package.rwsp")
    assert not (tmp_path / "outside.json").exists()
