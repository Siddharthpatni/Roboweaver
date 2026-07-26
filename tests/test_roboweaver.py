"""Comprehensive test suite for Universal RoboWeaver Platform."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from roboweaver.math3d import Mat3, Transform3D, Vec3
from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import (
    ROBOT_REGISTRY,
    NDOFIKSolver,
    WorkspaceSafetyGuard,
    forward_kinematics_ndof,
    get_franka_panda_spec,
    get_kuka_iiwa_spec,
    get_robot_spec,
    get_ur5e_spec,
)
from roboweaver.skills import IndustrialSkillCategory, get_industrial_skill_template
from roboweaver.fleet import FleetOrchestrator, SkillRetargeter
from roboweaver.codegen.groot2 import export_groot2_xml
from roboweaver.codegen.ros2_gen import generate_ros2_package
from roboweaver.registry import SkillPackage, SkillPackageMetadata, SkillRepository
from roboweaver.runtime import FailureMode, RecoveryAction, RecoveryEngine, SkillRuntime, TelemetryRecorder


class TestUniversalHardware(unittest.TestCase):
    def test_robot_profiles_registry(self):
        self.assertGreaterEqual(len(ROBOT_REGISTRY), 6)
        panda = get_robot_spec("panda")
        self.assertEqual(panda.dof, 7)
        ur5e = get_robot_spec("ur5e")
        self.assertEqual(ur5e.dof, 6)

    def test_ndof_kinematics_solve(self):
        panda = get_franka_panda_spec()
        solver = NDOFIKSolver(panda)
        target = Vec3(0.35, 0.0, 0.25)
        ok, q_sol, residual, iters = solver.solve(target)
        self.assertTrue(ok)
        self.assertEqual(len(q_sol), 7)

    def test_safety_guard(self):
        ur5e = get_ur5e_spec()
        guard = WorkspaceSafetyGuard(ur5e)
        res_safe = guard.validate_pose(Vec3(0.3, 0.0, 0.3))
        self.assertTrue(res_safe.is_safe)

        res_unsafe = guard.validate_pose(Vec3(5.0, 0.0, 0.3))
        self.assertFalse(res_unsafe.is_safe)


class TestIndustrialSkillTaxonomy(unittest.TestCase):
    def test_industrial_skill_templates(self):
        for cat in IndustrialSkillCategory:
            tmpl = get_industrial_skill_template(cat, "target_obj")
            self.assertGreater(len(tmpl.tasks), 0)
            self.assertIsNotNone(tmpl.behavior_tree_root)


class TestFleetRetargeting(unittest.TestCase):
    def test_cross_embodiment_retargeting(self):
        compiler = SkillCompiler(target_robot="panda")
        src_skill = compiler.compile("Pick up the red cube", verbose=False)

        retargeter = SkillRetargeter()
        res = retargeter.retarget(src_skill, "ur5e")
        self.assertTrue(res.success)
        self.assertEqual(res.target_robot_id, "ur5e")

    def test_fleet_orchestrator(self):
        orch = FleetOrchestrator()
        orch.add_robot_to_workcell("cell_1", "node_1", "panda")
        orch.add_robot_to_workcell("cell_1", "node_2", "ur5e")
        
        compiler = SkillCompiler(target_robot="panda")
        skill = compiler.compile("Pick up the red cube", verbose=False)
        meta = SkillPackageMetadata("demo", "Demo", "1.0.0", "Desc", "PICK", "red_cube")
        pkg = SkillPackage(meta, skill)

        res = orch.deploy_skill_to_fleet(pkg, "cell_1")
        self.assertTrue(res["node_1"])
        self.assertTrue(res["node_2"])


if __name__ == "__main__":
    unittest.main()
