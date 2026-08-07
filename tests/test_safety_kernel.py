"""
Verification suite for the Safety Kernel (plugins/safety_kernel.py) -- item 9 of
docs/COMPILER_ROADMAP.md's v2 vision.
"""

import dataclasses
import math

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import CompilerDiagnostic, SkillCompilationError
from roboweaver.plugins.backend import BACKEND_REGISTRY
from roboweaver.plugins.safety_kernel import SafetyKernel


def _real_result(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)


def test_enforce_is_a_noop_on_a_real_clean_result():
    print("\n[TEST 1] Testing SafetyKernel.enforce() is a no-op on a real compile result...")
    result = _real_result()
    SafetyKernel.enforce(result)  # must not raise
    print("  -> no exception for a real result (compile_with_diagnostics already refused any error) [PASSED]")


def test_enforce_blocks_a_directly_constructed_result_with_an_error_diagnostic():
    print("\n[TEST 2] Testing SafetyKernel.enforce() blocks a manually-constructed result with an injected error...")
    # Defense in depth: this is exactly the scenario compile_with_diagnostics()
    # can't happen through -- a CompilationResult reconstructed some other way,
    # here simulating a deserialized/tampered result carrying a real error diagnostic.
    result = _real_result()
    injected_error = CompilerDiagnostic(
        code="RW999", severity="error", message="Simulated tampered diagnostic",
        reason="test", required_capability=None,
    )
    tampered = dataclasses.replace(result, diagnostics=result.diagnostics + [injected_error])

    with pytest.raises(SkillCompilationError) as exc_info:
        SafetyKernel.enforce(tampered)
    assert exc_info.value.diagnostics[0].code == "RW999"
    print("  -> SkillCompilationError raised, carrying the injected error diagnostic [PASSED]")


def test_deploy_refuses_before_anything_else_when_safety_kernel_blocks():
    print("\n[TEST 3] Testing RobotBackend.deploy() refuses via the Safety Kernel before simulation/connect...")
    result = _real_result()
    injected_error = CompilerDiagnostic(
        code="RW999", severity="error", message="Simulated tampered diagnostic",
        reason="test", required_capability=None,
    )
    tampered = dataclasses.replace(result, diagnostics=result.diagnostics + [injected_error])

    backend = BACKEND_REGISTRY.get("ros2")
    with pytest.raises(SkillCompilationError):
        # skip_simulation_check=True proves the Safety Kernel step itself blocked
        # this -- not the simulation-validation step, which is bypassed here.
        backend.deploy(tampered, protocol="sim", uri="sim://127.0.0.1:1", skip_simulation_check=True)
    print("  -> deploy() refused via the Safety Kernel even with the simulation check skipped [PASSED]")


def test_enforce_revalidates_tampered_roboir_instead_of_trusting_old_diagnostics():
    result = _real_result()
    assert result.ir.lowering is not None
    first = result.ir.lowering.trajectories[0]
    bad_waypoint = (math.nan,) + first.waypoints[0][1:]
    bad_trajectory = dataclasses.replace(first, waypoints=(bad_waypoint,))
    result.ir = dataclasses.replace(
        result.ir,
        lowering=dataclasses.replace(
            result.ir.lowering,
            trajectories=(bad_trajectory,) + result.ir.lowering.trajectories[1:],
        ),
    )

    assert not any(d.severity == "error" for d in result.diagnostics)
    with pytest.raises(SkillCompilationError) as exc_info:
        SafetyKernel.enforce(result)
    assert any(
        d.code == "RW401" and "non-finite" in d.reason
        for d in exc_info.value.diagnostics
    )


if __name__ == "__main__":
    print("=== STARTING SAFETY KERNEL (ITEM 9) VERIFICATION ===")
    test_enforce_is_a_noop_on_a_real_clean_result()
    test_enforce_blocks_a_directly_constructed_result_with_an_error_diagnostic()
    test_deploy_refuses_before_anything_else_when_safety_kernel_blocks()
    print("\n=== ALL SAFETY KERNEL TESTS PASSED SUCCESSFULLY ===")
