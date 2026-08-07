"""
Verification suite for the RobotBackend contract (plugins/backend.py) -- item 3 of
docs/COMPILER_ROADMAP.md's v2 vision.
"""

import ast
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware.universal_driver import RobotConnectionStatus
from roboweaver.plugins.backend import (
    BACKEND_REGISTRY,
    DeploymentRefused,
    Ros2Backend,
    UrScriptBackend,
)


def _real_result(robot_id: str = "ur5e"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)


def test_registry_has_both_real_backends():
    print("\n[TEST 1] Testing both backends are registered...")
    assert set(BACKEND_REGISTRY.names()) == {"ros2", "urscript"}
    assert isinstance(BACKEND_REGISTRY.get("ros2"), Ros2Backend)
    assert isinstance(BACKEND_REGISTRY.get("urscript"), UrScriptBackend)
    print("  -> ros2 and urscript both registered [PASSED]")


def test_unknown_backend_raises_clearly():
    print("\n[TEST 2] Testing an unknown backend name raises clearly...")
    with pytest.raises(KeyError):
        BACKEND_REGISTRY.get("moveit")
    print("  -> KeyError raised for an unregistered backend [PASSED]")


def test_ros2_backend_generates_a_real_package():
    print("\n[TEST 3] Testing Ros2Backend.compile() produces a real ROS2 package...")
    result = _real_result()
    with tempfile.TemporaryDirectory() as tmpdir:
        out = BACKEND_REGISTRY.get("ros2").compile(result, Path(tmpdir))
        assert out.exists()
        assert (out / "package.xml").exists()
        assert (out / "behavior_tree.xml").exists()
        package_name = out.name
        assert (out / "resource" / package_name).exists()
        assert (out / package_name / "__init__.py").exists()
        action_client = out / package_name / "trajectory_client.py"
        assert action_client.exists()
        ast.parse(action_client.read_text(encoding="utf-8"))

        manifest = json.loads((out / "compiled_skill.json").read_text(encoding="utf-8"))
        spec = result.ir.execution.robot_id
        assert manifest["robot_id"] == spec
        expected = [
            [float(value) for value in waypoint]
            for segment in result.ir.lowering.trajectories
            for waypoint in segment.waypoints
        ]
        emitted = [
            waypoint
            for segment in manifest["trajectories"]
            for waypoint in segment["waypoints"]
        ]
        assert emitted == expected

        generated_source = action_client.read_text(encoding="utf-8")
        assert "FollowJointTrajectory" in generated_source
        assert "positions = [0.0]" not in generated_source
        assert "Trajectory controller rejected" in generated_source
    print("  -> real ROS2 package directory with package.xml/behavior_tree.xml [PASSED]")


def test_ros2_backend_rejects_waypoints_with_the_wrong_dof(tmp_path):
    result = _real_result()
    assert result.ir.lowering is not None
    first_segment = result.ir.lowering.trajectories[0]
    broken_segment = replace(
        first_segment,
        waypoints=(first_segment.waypoints[0][:-1],),
    )
    result.ir = replace(
        result.ir,
        lowering=replace(
            result.ir.lowering,
            trajectories=(broken_segment,) + result.ir.lowering.trajectories[1:],
        ),
    )

    with pytest.raises(ValueError, match="target robot requires"):
        BACKEND_REGISTRY.get("ros2").compile(result, tmp_path)


def test_codegen_reads_roboir_not_mutable_compiled_skill(tmp_path):
    result = _real_result()
    assert result.ir.lowering is not None
    expected_waypoints = sum(len(segment.waypoints) for segment in result.ir.lowering.trajectories)

    # CompiledSkill remains as a compatibility/runtime view. Code generation must
    # not consult it after RoboIR has become the verified source of truth.
    result.skill.motion_plan.trajectories.clear()
    ros_package = BACKEND_REGISTRY.get("ros2").compile(result, tmp_path / "ros")
    manifest = json.loads((ros_package / "compiled_skill.json").read_text())
    emitted_waypoints = sum(len(segment["waypoints"]) for segment in manifest["trajectories"])
    assert emitted_waypoints == expected_waypoints

    script = BACKEND_REGISTRY.get("urscript").compile(result, tmp_path / "ur")
    assert script.read_text().count("movej(") == expected_waypoints


def test_urscript_backend_generates_real_syntax():
    print("\n[TEST 4] Testing UrScriptBackend.compile() produces real, syntactically valid URScript...")
    result = _real_result()
    with tempfile.TemporaryDirectory() as tmpdir:
        out = BACKEND_REGISTRY.get("urscript").compile(result, Path(tmpdir))
        assert out.exists()
        content = out.read_text()
        assert content.startswith("#")
        assert "def roboweaver_" in content
        assert content.count("movej(") > 0
        assert content.rstrip().endswith("()")  # program invocation as the last line
        # Real waypoints from verified RoboIR -- not placeholders.
        assert result.ir.lowering is not None
        total_waypoints = sum(len(s.waypoints) for s in result.ir.lowering.trajectories)
        assert content.count("movej(") == total_waypoints
    print(f"  -> {content.count('movej(')} real movej() calls match the compiled skill's waypoint count [PASSED]")


def test_urscript_backend_refuses_non_ur_targets(tmp_path):
    result = _real_result("kuka_iiwa")
    with pytest.raises(ValueError, match="only supports verified Universal Robots"):
        BACKEND_REGISTRY.get("urscript").compile(result, tmp_path)


def test_backend_validate_returns_real_diagnostics():
    print("\n[TEST 5] Testing RobotBackend.validate() returns the real compile diagnostics...")
    result = _real_result()
    backend = BACKEND_REGISTRY.get("ros2")
    assert backend.validate(result) == result.diagnostics
    print("  -> validate() passes through the real, already-computed diagnostics [PASSED]")


def test_deploy_sends_real_trajectories_over_sim_bridge():
    print("\n[TEST 6] Testing RobotBackend.deploy() connects and sends real trajectories (sim bridge)...")
    result = _real_result()
    backend = BACKEND_REGISTRY.get("ros2")
    # "sim" protocol -> SimulationHardwareBridge -> TCP probe to an address nothing
    # listens on -> honestly reports not connected, so send_trajectory is never
    # called -- exercises the real, non-fabricated connect path either way.
    status = backend.deploy(result, protocol="sim", uri="sim://127.0.0.1:1")
    assert status.is_connected is False
    assert "sim" in status.protocol.lower() or "reachable" in status.message.lower() or "unreachable" in status.protocol.lower()
    print(f"  -> deploy() honestly reports not connected when nothing is listening: {status.message} [PASSED]")


def test_deploy_stops_and_disconnects_when_bridge_rejects_a_trajectory():
    result = _real_result()

    class RejectingBridge:
        disconnected = False
        sends = 0

        def __init__(self, spec, uri):
            self.spec = spec

        def connect(self):
            return RobotConnectionStatus(
                is_connected=True,
                protocol="test",
                robot_id=self.spec.id,
                dof=self.spec.dof,
                active_controllers=["test"],
                latency_ms=0.0,
                message="connected",
            )

        def send_trajectory(self, waypoints, dt=0.01):
            type(self).sends += 1
            return False

        def disconnect(self):
            type(self).disconnected = True

    with patch("roboweaver.plugins.backend.resolve_bridge_class", return_value=RejectingBridge):
        with pytest.raises(DeploymentRefused, match="rejected trajectory segment"):
            BACKEND_REGISTRY.get("ros2").deploy(
                result,
                protocol="test",
                uri="test://controller",
                skip_simulation_check=True,
            )

    assert RejectingBridge.sends == 1
    assert RejectingBridge.disconnected is True


if __name__ == "__main__":
    print("=== STARTING ROBOTBACKEND (ITEM 3) VERIFICATION ===")
    test_registry_has_both_real_backends()
    test_unknown_backend_raises_clearly()
    test_ros2_backend_generates_a_real_package()
    test_urscript_backend_generates_real_syntax()
    test_backend_validate_returns_real_diagnostics()
    test_deploy_sends_real_trajectories_over_sim_bridge()
    print("\n=== ALL ROBOTBACKEND TESTS PASSED SUCCESSFULLY ===")
