"""
Verification suite for fleet/orchestrator.py's real (not fabricated) deployment
outcome -- gap-fix batch, item 1c.
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.fleet.orchestrator import FleetOrchestrator
from roboweaver.registry.package import SkillPackage, SkillPackageMetadata


def test_deploy_reports_real_success_with_a_real_compiled_skill():
    print("\n[TEST 1] Regression: deploy_skill_to_fleet() still reports real success for a real skill...")
    orch = FleetOrchestrator()
    orch.add_robot_to_workcell("cell_1", "node_1", "panda")
    compiler = SkillCompiler(target_robot="panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    meta = SkillPackageMetadata("demo", "Demo", "1.0.0", "Desc", "PICK", "red_cube")
    pkg = SkillPackage(meta, skill)

    results = orch.deploy_skill_to_fleet(pkg, "cell_1")
    assert results["node_1"] is True
    assert orch.workcells["cell_1"].nodes[0].status == "EXECUTING"
    print("  -> real skill deploys with real success, status EXECUTING [PASSED]")


def test_deploy_reports_real_failure_when_skill_package_is_none():
    print("\n[TEST 2] Testing deploy_skill_to_fleet(None, ...) reports real failure, not fabricated success...")
    orch = FleetOrchestrator()
    orch.add_robot_to_workcell("cell_1", "node_1", "panda")

    results = orch.deploy_skill_to_fleet(None, "cell_1")
    assert results["node_1"] is False
    node = orch.workcells["cell_1"].nodes[0]
    assert node.status == "ERROR"
    assert node.active_skill_id is None
    print("  -> real failure reported: status=ERROR, result=False, no fabricated EXECUTING [PASSED]")


def test_deploy_reports_real_failure_when_skill_body_is_none():
    print("\n[TEST 3] Testing deploy_skill_to_fleet() reports real failure when the package has no compiled body...")
    orch = FleetOrchestrator()
    orch.add_robot_to_workcell("cell_1", "node_1", "panda")
    meta = SkillPackageMetadata("demo", "Demo", "1.0.0", "Desc", "PICK", "red_cube")
    empty_pkg = SkillPackage(meta, skill=None)

    results = orch.deploy_skill_to_fleet(empty_pkg, "cell_1")
    assert results["node_1"] is False
    assert orch.workcells["cell_1"].nodes[0].status == "ERROR"
    print("  -> real failure reported for a metadata-only package with no compiled skill [PASSED]")


if __name__ == "__main__":
    print("=== STARTING FLEET ORCHESTRATOR (GAP-FIX ITEM 1c) VERIFICATION ===")
    test_deploy_reports_real_success_with_a_real_compiled_skill()
    test_deploy_reports_real_failure_when_skill_package_is_none()
    test_deploy_reports_real_failure_when_skill_body_is_none()
    print("\n=== ALL FLEET ORCHESTRATOR TESTS PASSED SUCCESSFULLY ===")
