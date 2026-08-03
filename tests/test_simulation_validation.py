"""
Verification suite for the Compile -> Twin -> Test -> Deploy gate (item 5 of
docs/COMPILER_ROADMAP.md's v2 vision): runtime/validation.py wired into
plugins/backend.py::RobotBackend.deploy().
"""

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.plugins.backend import BACKEND_REGISTRY, DeploymentRefused
from roboweaver.runtime.validation import validate_in_simulation


def test_validate_in_simulation_succeeds_for_a_real_pick_skill():
    print("\n[TEST 1] Testing validate_in_simulation() really executes a successful pick skill...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Pick up the red cube", verbose=False)
    spec = get_robot_spec("franka_panda")

    result = validate_in_simulation(skill, spec)
    assert result.success is True
    print(f"  -> real successful simulation, height_gained={result.height_gained:.3f}m [PASSED]")


def test_deploy_refuses_when_simulation_genuinely_fails():
    print("\n[TEST 2] Testing deploy() refuses via DeploymentRefused on a real simulation failure...")
    # A real, naturally-occurring failure -- TIGHTEN's task descriptions don't match
    # any motion_plan entry (RW502), so the arm never actually moves toward the
    # target in NativeTwin's simulation and the grasp genuinely fails. Not
    # constructed/fabricated -- this is real compiler behavior today.
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Tighten the M8 bolt", verbose=False)
    backend = BACKEND_REGISTRY.get("ros2")

    with pytest.raises(DeploymentRefused) as exc_info:
        backend.deploy(result, protocol="sim", uri="sim://127.0.0.1:1")
    assert exc_info.value.execution_result is not None
    assert exc_info.value.execution_result.success is False
    print(f"  -> DeploymentRefused raised before any bridge connect attempt: {exc_info.value} [PASSED]")


def test_deploy_skip_simulation_check_is_an_explicit_opt_out():
    print("\n[TEST 3] Testing skip_simulation_check=True bypasses the twin gate explicitly...")
    compiler = SkillCompiler(target_robot="franka_panda")
    result = compiler.compile_with_diagnostics("Tighten the M8 bolt", verbose=False)
    backend = BACKEND_REGISTRY.get("ros2")

    # Same failing skill as above, but the caller explicitly opted out of the
    # simulation gate -- so deploy() proceeds straight to the (honestly
    # unreachable) bridge connect instead of raising.
    status = backend.deploy(
        result, protocol="sim", uri="sim://127.0.0.1:1", skip_simulation_check=True,
    )
    assert status.is_connected is False
    print(f"  -> no DeploymentRefused; reached the real bridge connect attempt instead [PASSED]")


if __name__ == "__main__":
    print("=== STARTING SIMULATION VALIDATION GATE (ITEM 5) VERIFICATION ===")
    test_validate_in_simulation_succeeds_for_a_real_pick_skill()
    test_deploy_refuses_when_simulation_genuinely_fails()
    test_deploy_skip_simulation_check_is_an_explicit_opt_out()
    print("\n=== ALL SIMULATION VALIDATION TESTS PASSED SUCCESSFULLY ===")
