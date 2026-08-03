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
value is defense in depth: it protects plugins/backend.py::RobotBackend.deploy() (and
any future caller) against a CompilationResult that reached it through some *other*
path -- constructed directly, deserialized from a file, reconstructed from a partial
record -- none of which are guaranteed to have gone through the enforcing compile
path.  Mandatory at RobotBackend.deploy() (brand-new code, breaks nothing existing);
deliberately NOT made mandatory on SkillRuntime.execute() -- pure simulation, called
directly with a bare CompiledSkill throughout the existing CLI/fleet/test suite,
never the real hardware boundary. Stated plainly, not silently scoped down.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from roboweaver.ir.diagnostics import SkillCompilationError

if TYPE_CHECKING:
    from roboweaver.compiler import CompilationResult


class SafetyKernel:
    @staticmethod
    def enforce(result: "CompilationResult") -> None:
        """Raises SkillCompilationError (the existing type -- no new exception
        needed) if `result.diagnostics` contains any error-severity diagnostic.
        Nothing here is recomputed; these diagnostics are already real."""
        errors = [d for d in result.diagnostics if d.severity == "error"]
        if errors:
            raise SkillCompilationError(errors)

    @staticmethod
    def build_deployment_manifest(result: "CompilationResult", backend_name: str) -> dict[str, Any]:
        """Real manifest for item 13 (docs/COMPILER_ROADMAP.md v2 vision):
        robot id, backend used, this compile's actual diagnostic counts (proof the
        Safety Kernel check passed -- `safety_kernel_verified` is computed from the
        same real diagnostics `enforce()` checks, not asserted), and the real
        capability claims (item 2). Bundled into the .rwsp archive by
        registry/package.py::SkillPackage.export_archive()."""
        errors = [d for d in result.diagnostics if d.severity == "error"]
        warnings = [d for d in result.diagnostics if d.severity == "warning"]
        return {
            "robot_id": result.ir.execution.robot_id,
            "backend": backend_name,
            "safety_kernel_verified": len(errors) == 0,
            "diagnostic_summary": {"error_count": len(errors), "warning_count": len(warnings)},
            "capability_claims": [c.to_dict() for c in result.ir.required_capabilities.claims],
        }
