"""
Verification suite for the Compile -> Twin -> Test -> Deploy gate (item 5 of
docs/COMPILER_ROADMAP.md's v2 vision): runtime/validation.py wired into
plugins/backend.py::RobotBackend.deploy().
"""

import dataclasses

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.ir import SkillCompilationError
from roboweaver.plugins.backend import BACKEND_REGISTRY, DeploymentRefused
from roboweaver.runtime.validation import validate_in_simulation


def test_validate_in_simulation_succeeds_for_a_real_pick_skill():
    print("\n[TEST 1] Testing validate_in_simulation() really executes a successful pick skill...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    spec = get_robot_spec("franka_panda")

    result = validate_in_simulation(skill, spec)
    assert result.success is True
    assert result.validation_level == "process_model"
    assert "object_lift" in result.validated_claims
    print(f"  -> real successful simulation, height_gained={result.height_gained:.3f}m [PASSED]")


def test_simulation_can_execute_verified_roboir_without_compiled_skill():
    compiler = SkillCompiler(target_robot="franka_panda")
    compiled = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    compiled.skill.motion_plan.trajectories.clear()

    result = validate_in_simulation(compiled.ir, compiler.robot_spec)
    assert result.success is True
    assert result.validation_level == "process_model"


def test_unmodeled_process_task_never_passes_on_motion_alone():
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Weld the steel bracket seam", verbose=False)
    result = validate_in_simulation(skill, compiler.robot_spec)

    assert result.success is False
    assert result.validation_level == "kinematic_only"
    assert result.unsupported_claims == ["weld_process_outcome"]
    assert "no action-specific WELD process model" in result.failure_reason


def _skill_with_a_joint_limit_violating_segment(result):
    """Deliberately constructed (not naturally occurring, since the gap-fix batch's
    generalized _plan_motion now succeeds cleanly for every registered robot/
    category): mutates the *last* segment's final real waypoint far outside any real
    joint limit (runtime/engine.py sets self.qpos from each segment's actual
    waypoints, not from start_pose/end_pose, which are metadata only), so
    NativeTwin's real _check_joint_limits() genuinely fails at the end of execution."""
    assert result.ir.lowering is not None
    trajectories = list(result.ir.lowering.trajectories)
    seg = trajectories[-1]
    dof = len(seg.waypoints[-1])
    broken_waypoints = seg.waypoints[:-1] + (tuple([999.0] * dof),)
    broken = dataclasses.replace(
        seg,
        end_pose=tuple([999.0] * dof),
        waypoints=broken_waypoints,
    )
    trajectories[-1] = broken
    broken_lowering = dataclasses.replace(
        result.ir.lowering,
        trajectories=tuple(trajectories),
    )
    return dataclasses.replace(
        result,
        ir=dataclasses.replace(result.ir, lowering=broken_lowering),
    )


def test_native_simulation_genuinely_fails_for_invalid_joint_motion():
    print("\n[TEST 2] Testing NativeTwin reports a real joint-limit failure...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    broken_result = _skill_with_a_joint_limit_violating_segment(result)
    execution = validate_in_simulation(broken_result.ir, compiler.robot_spec)
    assert execution.success is False
    assert execution.joint_limits_respected is False
    print("  -> NativeTwin returned a measured joint-limit failure [PASSED]")


def test_deploy_cannot_bypass_revalidated_safety_with_simulation_opt_out():
    print("\n[TEST 3] Testing simulation opt-out cannot bypass the Safety Kernel...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    broken_result = _skill_with_a_joint_limit_violating_segment(result)
    backend = BACKEND_REGISTRY.get("ros2")

    # The opt-out covers only process simulation. Structural and safety validation
    # are mandatory and are recomputed from the exact IR at deployment time.
    with pytest.raises(SkillCompilationError) as exc_info:
        backend.deploy(
            broken_result,
            protocol="sim",
            uri="sim://127.0.0.1:1",
            skip_simulation_check=True,
        )
    assert any(d.code in {"RW302", "RW304"} for d in exc_info.value.diagnostics)
    print("  -> mandatory safety revalidation blocked the tampered IR [PASSED]")


def test_physical_deploy_refuses_assumed_object_poses():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the red cube", verbose=False,
    )
    with pytest.raises(DeploymentRefused, match="requires measured or user-specified"):
        BACKEND_REGISTRY.get("ros2").deploy(
            result, protocol="ros2", uri="ros2://robot-controller"
        )


def test_physical_deploy_cannot_bypass_simulation_gate():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the red cube", verbose=False,
    )
    with pytest.raises(DeploymentRefused, match="cannot bypass simulation"):
        BACKEND_REGISTRY.get("ros2").deploy(
            result,
            protocol="ros2",
            uri="ros2://robot-controller",
            skip_simulation_check=True,
        )


if __name__ == "__main__":
    print("=== STARTING SIMULATION VALIDATION GATE (ITEM 5) VERIFICATION ===")
    test_validate_in_simulation_succeeds_for_a_real_pick_skill()
    test_native_simulation_genuinely_fails_for_invalid_joint_motion()
    test_deploy_cannot_bypass_revalidated_safety_with_simulation_opt_out()
    print("\n=== ALL SIMULATION VALIDATION TESTS PASSED SUCCESSFULLY ===")
