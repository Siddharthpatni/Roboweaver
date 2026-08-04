"""
Verification suite for the Compile -> Twin -> Test -> Deploy gate (item 5 of
docs/COMPILER_ROADMAP.md's v2 vision): runtime/validation.py wired into
plugins/backend.py::RobotBackend.deploy().
"""

import dataclasses

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.plugins.backend import BACKEND_REGISTRY, DeploymentRefused
from roboweaver.runtime.validation import validate_in_simulation
from roboweaver.types import TrajectorySegment


def test_validate_in_simulation_succeeds_for_a_real_pick_skill():
    print("\n[TEST 1] Testing validate_in_simulation() really executes a successful pick skill...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    spec = get_robot_spec("franka_panda")

    result = validate_in_simulation(skill, spec)
    assert result.success is True
    print(f"  -> real successful simulation, height_gained={result.height_gained:.3f}m [PASSED]")


def _skill_with_a_joint_limit_violating_segment(result):
    """Deliberately constructed (not naturally occurring, since the gap-fix batch's
    generalized _plan_motion now succeeds cleanly for every registered robot/
    category): mutates the *last* segment's final real waypoint far outside any real
    joint limit (runtime/engine.py sets self.qpos from each segment's actual
    waypoints, not from start_pose/end_pose, which are metadata only), so
    NativeTwin's real _check_joint_limits() genuinely fails at the end of execution."""
    trajectories = dict(result.skill.motion_plan.trajectories)
    last_name = list(trajectories.keys())[-1]
    seg = trajectories[last_name]
    dof = len(seg.waypoints[-1])
    broken_waypoints = list(seg.waypoints[:-1]) + [[999.0] * dof]
    broken = TrajectorySegment(
        start_pose=seg.start_pose, end_pose=[999.0] * dof,
        waypoints=broken_waypoints, duration=seg.duration,
    )
    trajectories[last_name] = broken
    new_motion_plan = dataclasses.replace(result.skill.motion_plan, trajectories=trajectories)
    broken_skill = dataclasses.replace(result.skill, motion_plan=new_motion_plan)
    return dataclasses.replace(result, skill=broken_skill)


def test_deploy_refuses_when_simulation_genuinely_fails():
    print("\n[TEST 2] Testing deploy() refuses via DeploymentRefused on a real simulation failure...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    broken_result = _skill_with_a_joint_limit_violating_segment(result)
    backend = BACKEND_REGISTRY.get("ros2")

    with pytest.raises(DeploymentRefused) as exc_info:
        backend.deploy(broken_result, protocol="sim", uri="sim://127.0.0.1:1")
    assert exc_info.value.execution_result is not None
    assert exc_info.value.execution_result.success is False
    assert exc_info.value.execution_result.joint_limits_respected is False
    print(f"  -> DeploymentRefused raised before any bridge connect attempt: {exc_info.value} [PASSED]")


def test_deploy_skip_simulation_check_is_an_explicit_opt_out():
    print("\n[TEST 3] Testing skip_simulation_check=True bypasses the twin gate explicitly...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    broken_result = _skill_with_a_joint_limit_violating_segment(result)
    backend = BACKEND_REGISTRY.get("ros2")

    # Same deliberately-broken skill as above, but the caller explicitly opted out
    # of the simulation gate -- so deploy() proceeds straight to the (honestly
    # unreachable) bridge connect instead of raising.
    status = backend.deploy(
        broken_result, protocol="sim", uri="sim://127.0.0.1:1", skip_simulation_check=True,
    )
    assert status.is_connected is False
    print(f"  -> no DeploymentRefused; reached the real bridge connect attempt instead [PASSED]")


if __name__ == "__main__":
    print("=== STARTING SIMULATION VALIDATION GATE (ITEM 5) VERIFICATION ===")
    test_validate_in_simulation_succeeds_for_a_real_pick_skill()
    test_deploy_refuses_when_simulation_genuinely_fails()
    test_deploy_skip_simulation_check_is_an_explicit_opt_out()
    print("\n=== ALL SIMULATION VALIDATION TESTS PASSED SUCCESSFULLY ===")
