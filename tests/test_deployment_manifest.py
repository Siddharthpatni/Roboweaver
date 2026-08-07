"""
Verification suite for the industrial deployment manifest (registry/package.py +
plugins/safety_kernel.py::build_deployment_manifest) -- item 13 of
docs/COMPILER_ROADMAP.md's v2 vision.
"""

import json
import hashlib
import tarfile
import tempfile
from pathlib import Path

from roboweaver.compiler import SkillCompiler
from roboweaver.codegen.groot2 import export_groot2_ir
from roboweaver.plugins.safety_kernel import SafetyKernel
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata


def _real_result(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)


def test_build_deployment_manifest_reflects_real_diagnostics_and_claims():
    print("\n[TEST 1] Testing build_deployment_manifest() reflects real diagnostics/claims...")
    result = _real_result()
    manifest = SafetyKernel.build_deployment_manifest(result, backend_name="ros2")

    assert manifest["robot_id"] == "franka_panda"
    assert manifest["backend"] == "ros2"
    assert manifest["safety_kernel_verified"] is True  # compile_with_diagnostics already refused any error
    canonical_ir = json.dumps(
        result.ir.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    assert manifest["ir_sha256"] == hashlib.sha256(canonical_ir).hexdigest()
    assert manifest["roboir"] == result.ir.to_dict()
    assert manifest["collision_check"] is False
    assert manifest["diagnostic_summary"]["error_count"] == 0
    assert manifest["capability_claims"] == [c.to_dict() for c in result.ir.required_capabilities.claims]
    print(f"  -> real manifest: {manifest['diagnostic_summary']}, "
          f"{len(manifest['capability_claims'])} capability claims [PASSED]")


def test_export_archive_without_manifest_is_unaffected():
    print("\n[TEST 2] Testing export_archive() without deployment_manifest is unchanged (backward compatible)...")
    result = _real_result()
    meta = SkillPackageMetadata(
        id="pkg_no_manifest", name="Test", version="1.0.0", description="test",
        action="PICK", target_object="red_cube",
    )
    pkg = SkillPackage(meta, result.skill)
    with tempfile.TemporaryDirectory() as tmpdir:
        archive = pkg.export_archive(Path(tmpdir) / "test.rwsp")
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
        assert "deployment_manifest.json" not in names
        assert "metadata.json" in names
        assert "package_data.json" in names
    print("  -> no deployment_manifest.json in the archive when none is passed [PASSED]")


def test_export_archive_with_manifest_bundles_it_into_the_rwsp():
    print("\n[TEST 3] Testing export_archive(deployment_manifest=...) bundles a real manifest into the .rwsp...")
    result = _real_result()
    manifest = SafetyKernel.build_deployment_manifest(result, backend_name="urscript")
    meta = SkillPackageMetadata(
        id="pkg_with_manifest", name="Test", version="1.0.0", description="test",
        action="PICK", target_object="red_cube",
    )
    pkg = SkillPackage(meta, result.skill)
    with tempfile.TemporaryDirectory() as tmpdir:
        archive = pkg.export_archive(
            Path(tmpdir) / "test.rwsp",
            deployment_manifest=manifest,
            roboir=result.ir,
        )
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            assert "deployment_manifest.json" in names
            extracted = tar.extractfile("deployment_manifest.json")
            on_disk = json.loads(extracted.read())
            behavior = tar.extractfile("behavior_tree.xml")
            behavior_xml = behavior.read().decode("utf-8")
        assert on_disk == manifest
        assert on_disk["backend"] == "urscript"
        assert behavior_xml == export_groot2_ir(result.ir)
    print("  -> real deployment_manifest.json bundled into the .rwsp archive, round-trips exactly [PASSED]")


if __name__ == "__main__":
    print("=== STARTING DEPLOYMENT MANIFEST (ITEM 13) VERIFICATION ===")
    test_build_deployment_manifest_reflects_real_diagnostics_and_claims()
    test_export_archive_without_manifest_is_unaffected()
    test_export_archive_with_manifest_bundles_it_into_the_rwsp()
    print("\n=== ALL DEPLOYMENT MANIFEST TESTS PASSED SUCCESSFULLY ===")
