"""
Safety Kernel (docs/COMPILER_ROADMAP.md v2 vision, item 9): a single, centralized,
non-bypassable enforcement point wrapping the compile pipeline's already-real
diagnostics -- not a new safety check, a mandatory gate on the ones that already
exist (RoboIRVerificationPass/CapabilityPass/SafetyPass, ir/pass_manager.py;
CompiledSkillVerificationPass, optimize/pass_manager.py).

Honesty note on what this actually adds: SkillCompiler.compile_with_diagnostics()
already raises SkillCompilationError before returning any CompilationResult that has
an error-severity diagnostic -- so on the normal compile path, `enforce()` below can
never actually find an error; it's structurally unreachable via that route.  Its real
value is defense in depth: it protects plugins/backend.py::RobotBackend.deploy()
against a CompilationResult that was deserialized, reconstructed, or modified after
compilation. The kernel re-runs structural, capability, and safety checks on the
exact RoboIR being deployed instead of trusting a stale diagnostics list. Mandatory
at RobotBackend.deploy();
deliberately NOT made mandatory on SkillRuntime.execute() -- pure simulation, called
directly with a bare CompiledSkill throughout the existing CLI/fleet/test suite,
never the real hardware boundary. Stated plainly, not silently scoped down.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TYPE_CHECKING

from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.ir.diagnostics import (
    CompilerDiagnostic,
    SkillCompilationError,
    check_required_capabilities,
)
from roboweaver.ir.pass_manager import PassContext
from roboweaver.ir.passes import RoboIRVerificationPass
from roboweaver.ir.safety import check_safety

if TYPE_CHECKING:
    from roboweaver.compiler import CompilationResult


class SafetyKernel:
    @staticmethod
    def enforce(result: "CompilationResult") -> None:
        """Revalidate the exact deployment IR and reject every error."""
        errors = [d for d in result.diagnostics if d.severity == "error"]
        try:
            robot_spec = get_robot_spec(result.ir.execution.robot_id)
        except (KeyError, ValueError) as exc:
            errors.append(
                CompilerDiagnostic(
                    code="RW401",
                    severity="error",
                    message="Deployment RoboIR names an unknown or invalid robot target.",
                    reason=str(exc),
                    required_capability=None,
                    fixes=["Recompile against a registered, valid RobotSpec."],
                )
            )
        else:
            context = PassContext(ir=result.ir, skill=result.skill, robot_spec=robot_spec)
            structural = RoboIRVerificationPass().run(context).diagnostics
            errors.extend(d for d in structural if d.severity == "error")
            if not any(d.severity == "error" for d in structural):
                errors.extend(
                    d
                    for d in check_required_capabilities(result.ir, robot_spec)
                    if d.severity == "error"
                )
                errors.extend(
                    d for d in check_safety(result.ir, robot_spec) if d.severity == "error"
                )
        if errors:
            deduplicated = list({(d.code, d.message, d.reason): d for d in errors}.values())
            raise SkillCompilationError(deduplicated)

    @staticmethod
    def build_deployment_manifest(result: "CompilationResult", backend_name: str) -> dict[str, Any]:
        """Create an auditable manifest only after mandatory IR revalidation."""
        SafetyKernel.enforce(result)
        errors = [d for d in result.diagnostics if d.severity == "error"]
        warnings = [d for d in result.diagnostics if d.severity == "warning"]
        roboir = result.ir.to_dict()
        canonical_ir = json.dumps(
            roboir, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return {
            "manifest_version": 2,
            "skill_id": result.ir.skill_id,
            "robot_id": result.ir.execution.robot_id,
            "backend": backend_name,
            "ir_version": result.ir.ir_version,
            "ir_sha256": hashlib.sha256(canonical_ir).hexdigest(),
            "safety_kernel_verified": True,
            "collision_check": result.ir.verification.collision_check,
            "diagnostic_summary": {"error_count": len(errors), "warning_count": len(warnings)},
            "capability_claims": [c.to_dict() for c in result.ir.required_capabilities.claims],
            "roboir": roboir,
        }
