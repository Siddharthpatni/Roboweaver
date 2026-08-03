"""
Structural + wrapped diagnostic passes for the Pass Manager (ir/pass_manager.py).

RoboIRVerificationPass is new logic -- nothing in RoboWeaver checked RoboIR's own
structural invariants before this pass existed. CapabilityPass and SafetyPass are
thin wrappers around the pre-existing check_required_capabilities()/check_safety()
functions (ir/diagnostics.py, ir/safety.py) -- unchanged behavior and diagnostic
codes, just run through the Pass Manager instead of called directly by compiler.py.
"""

from __future__ import annotations

from typing import get_args

from roboweaver.ir.diagnostics import CompilerDiagnostic, check_required_capabilities
from roboweaver.ir.pass_manager import CompilerPass, PassContext, PassResult
from roboweaver.ir.safety import check_safety
from roboweaver.ir.schema import ObjectRole

_VALID_OBJECT_ROLES = set(get_args(ObjectRole))

# Every safety_checks name ir/safety.py::check_safety() actually implements. Kept as
# an explicit set here (rather than introspecting check_safety) so a typo'd name in
# VerificationSpec.safety_checks is caught even though check_safety() itself always
# runs every check it has regardless of what this list says.
_KNOWN_SAFETY_CHECKS = {"reach", "floor", "payload", "joint_limits", "velocity", "manipulability"}


class RoboIRVerificationPass(CompilerPass):
    """Structural invariant checks on a RoboIR itself, independent of any target
    robot's capabilities. Every current build_ir() output already satisfies all of
    these -- this pass is a regression guard for future IR-producing/mutating passes
    (docs/COMPILER_ROADMAP.md Phase 3/4), not a check on anything build_ir() has ever
    gotten wrong. Runs first in the default pipeline (compiler.py), on the theory that
    checking an IR's own shape should happen before checking it against a robot."""

    name = "RoboIRVerificationPass"

    def run(self, ctx: PassContext) -> PassResult:
        ir = ctx.ir
        violations: list[str] = []

        if not ir.skill_id:
            violations.append("skill_id is empty")

        parts = ir.ir_version.split(".") if isinstance(ir.ir_version, str) else []
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            violations.append(f"ir_version {ir.ir_version!r} is not a well-formed N.N.N version")

        seen_ids: set[str] = set()
        for obj in ir.objects:
            if obj.id in seen_ids:
                violations.append(f"duplicate object id {obj.id!r}")
            seen_ids.add(obj.id)
            if obj.role not in _VALID_OBJECT_ROLES:
                violations.append(f"object {obj.id!r} has unrecognised role {obj.role!r}")

        if ir.execution.robot_id != ctx.robot_spec.id:
            violations.append(
                f"execution.robot_id {ir.execution.robot_id!r} does not match "
                f"target robot {ctx.robot_spec.id!r}"
            )
        if ir.execution.dof != ctx.robot_spec.dof:
            violations.append(
                f"execution.dof {ir.execution.dof} does not match "
                f"target robot's declared dof {ctx.robot_spec.dof}"
            )

        if ir.constraints.payload_kg is not None and ir.constraints.payload_kg < 0:
            violations.append(f"constraints.payload_kg is negative ({ir.constraints.payload_kg})")

        unknown_checks = set(ir.verification.safety_checks) - _KNOWN_SAFETY_CHECKS
        if unknown_checks:
            violations.append(
                f"verification.safety_checks names unknown check(s): {sorted(unknown_checks)}"
            )

        diagnostics: list[CompilerDiagnostic] = []
        if violations:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW401",
                    severity="error",
                    message=(
                        f"RoboIR '{ir.skill_id}' failed structural verification "
                        f"({len(violations)} violation(s))."
                    ),
                    reason="; ".join(violations),
                    required_capability=None,
                    fixes=[
                        "This indicates a bug in whichever pass produced this RoboIR "
                        "(build_ir() or an IR-mutating pass) -- not a user-fixable input.",
                    ],
                )
            )

        return PassResult(
            ir=ir, diagnostics=diagnostics, metrics={"violations": float(len(violations))}
        )


class CapabilityPass(CompilerPass):
    """Thin wrapper around ir/diagnostics.py::check_required_capabilities() -- same
    diagnostics, same codes (RW102, RW201), now run through the Pass Manager."""

    name = "CapabilityPass"

    def run(self, ctx: PassContext) -> PassResult:
        diagnostics = check_required_capabilities(ctx.ir, ctx.robot_spec)
        return PassResult(
            ir=ctx.ir, diagnostics=diagnostics, metrics={"diagnostic_count": float(len(diagnostics))}
        )


class SafetyPass(CompilerPass):
    """Thin wrapper around ir/safety.py::check_safety() -- same diagnostics, same
    codes (RW301-RW306), now run through the Pass Manager."""

    name = "SafetyPass"

    def run(self, ctx: PassContext) -> PassResult:
        diagnostics = check_safety(ctx.skill, ctx.ir, ctx.robot_spec)
        return PassResult(
            ir=ctx.ir, diagnostics=diagnostics, metrics={"diagnostic_count": float(len(diagnostics))}
        )
