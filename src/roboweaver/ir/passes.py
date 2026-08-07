"""
Structural + wrapped diagnostic passes for the Pass Manager (ir/pass_manager.py).

RoboIRVerificationPass is new logic -- nothing in RoboWeaver checked RoboIR's own
structural invariants before this pass existed. CapabilityPass and SafetyPass are
thin wrappers around the pre-existing check_required_capabilities()/check_safety()
functions (ir/diagnostics.py, ir/safety.py) -- unchanged behavior and diagnostic
codes, just run through the Pass Manager instead of called directly by compiler.py.
"""

from __future__ import annotations

import math
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
_KNOWN_SAFETY_CHECKS = {
    "reach", "floor", "payload", "joint_limits", "velocity", "manipulability",
    "environment_collision",
}


def _verify_header(ir, robot_spec) -> list[str]:
    violations: list[str] = []
    if not ir.skill_id:
        violations.append("skill_id is empty")
    parts = ir.ir_version.split(".") if isinstance(ir.ir_version, str) else []
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        violations.append(f"ir_version {ir.ir_version!r} is not a well-formed N.N.N version")
    seen_ids: set[str] = set()
    for obj in ir.objects:
        if obj.id in seen_ids:
            violations.append(f"duplicate object id {obj.id!r}")
        seen_ids.add(obj.id)
        if obj.role not in _VALID_OBJECT_ROLES:
            violations.append(f"object {obj.id!r} has unrecognised role {obj.role!r}")
    if ir.execution.robot_id != robot_spec.id:
        violations.append(
            f"execution.robot_id {ir.execution.robot_id!r} does not match target robot {robot_spec.id!r}"
        )
    if ir.execution.dof != robot_spec.dof:
        violations.append(
            f"execution.dof {ir.execution.dof} does not match target robot's declared dof {robot_spec.dof}"
        )
    return violations


def _verify_presence(ir) -> list[str]:
    violations: list[str] = []
    if (ir.program is None) != (ir.lowering is None):
        violations.append("program and lowering must either both be present or both be absent")
    if ir.task_summary is not None and ir.program is None:
        violations.append("task_summary exists but complete program data is absent")
    if ir.motion_summary is not None and ir.lowering is None:
        violations.append("motion_summary exists but complete lowering data is absent")
    return violations


def _verify_lowering_header(ir, robot_spec) -> list[str]:
    violations: list[str] = []
    if ir.lowering.robot_id != ir.execution.robot_id:
        violations.append(
            f"lowering.robot_id {ir.lowering.robot_id!r} does not match execution.robot_id {ir.execution.robot_id!r}"
        )
    if len(ir.lowering.joint_names) != ir.execution.dof:
        violations.append(
            f"lowering declares {len(ir.lowering.joint_names)} joint names for execution.dof={ir.execution.dof}"
        )
    expected = tuple(joint.name for joint in robot_spec.joints[: robot_spec.dof])
    if tuple(ir.lowering.joint_names) != expected:
        violations.append("lowering joint names do not exactly match the target RobotSpec")
    if not math.isfinite(ir.program.confidence) or not 0.0 <= ir.program.confidence <= 1.0:
        violations.append("program confidence is not finite and within [0, 1]")
    has_perception = any(task.type == "PERCEIVE" for task in ir.program.tasks)
    if has_perception and not ir.required_capabilities.perception:
        violations.append("program contains PERCEIVE but required_capabilities.perception is empty")
    move_tasks = [task.description for task in ir.program.tasks if task.type == "MOVE_TO"]
    trajectory_tasks = [item.task_description for item in ir.lowering.trajectories]
    if move_tasks != trajectory_tasks:
        violations.append("lowered trajectory order does not exactly match MOVE_TO task order")
    return violations


def _verify_trajectory(trajectory, dof: int) -> list[str]:
    violations: list[str] = []
    label = trajectory.task_description
    if not math.isfinite(trajectory.duration_s) or trajectory.duration_s < 0.0:
        violations.append(f"trajectory {label!r} has invalid duration")
    for pose_label, pose in (("start", trajectory.start_pose), ("end", trajectory.end_pose)):
        if len(pose) != dof:
            violations.append(f"trajectory {label!r} {pose_label} pose has {len(pose)} positions for dof={dof}")
        elif not all(math.isfinite(value) for value in pose):
            violations.append(f"trajectory {label!r} {pose_label} pose is non-finite")
    if not trajectory.waypoints:
        violations.append(f"trajectory {label!r} has no waypoints")
    for index, waypoint in enumerate(trajectory.waypoints):
        if len(waypoint) != dof:
            violations.append(f"trajectory {label!r} waypoint {index} has {len(waypoint)} positions for dof={dof}")
        elif not all(math.isfinite(value) for value in waypoint):
            violations.append(f"trajectory {label!r} waypoint {index} is non-finite")
    return violations


def _verify_solution(solution, dof: int) -> list[str]:
    violations: list[str] = []
    label = solution.task_description
    if len(solution.joint_angles) != dof:
        violations.append(f"IK solution {label!r} has {len(solution.joint_angles)} joints for dof={dof}")
    elif not all(math.isfinite(value) for value in solution.joint_angles):
        violations.append(f"IK solution {label!r} is non-finite")
    if len(solution.target_position) != 3 or not all(math.isfinite(value) for value in solution.target_position):
        violations.append(f"IK solution {label!r} has an invalid target position")
    if not math.isfinite(solution.residual_m) or solution.residual_m < 0.0:
        violations.append(f"IK solution {label!r} has an invalid residual")
    if solution.iterations < 0:
        violations.append(f"IK solution {label!r} has negative iterations")
    return violations


def _verify_summaries(ir) -> list[str]:
    violations: list[str] = []
    if ir.task_summary is not None:
        if ir.task_summary.task_count != len(ir.program.tasks):
            violations.append("task_summary.task_count does not match program.tasks")
        if ir.task_summary.task_types != tuple(task.type for task in ir.program.tasks):
            violations.append("task_summary.task_types does not match program.tasks")
    if ir.motion_summary is not None:
        waypoint_count = sum(len(item.waypoints) for item in ir.lowering.trajectories)
        if ir.motion_summary.segment_count != len(ir.lowering.trajectories):
            violations.append("motion_summary.segment_count does not match lowering")
        if ir.motion_summary.total_waypoints != waypoint_count:
            violations.append("motion_summary.total_waypoints does not match lowering")
    return violations


def _verification_diagnostic(ir, violations: list[str]) -> list[CompilerDiagnostic]:
    if not violations:
        return []
    return [CompilerDiagnostic(
        code="RW401", severity="error",
        message=f"RoboIR '{ir.skill_id}' failed structural verification ({len(violations)} violation(s)).",
        reason="; ".join(violations), required_capability=None,
        fixes=["This indicates a bug in whichever pass produced this RoboIR (build_ir() or an IR-mutating pass) -- not a user-fixable input."],
    )]


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
        structure = ctx.analyses.get("roboir.structure", ctx)
        violations = _verify_header(ir, ctx.robot_spec)
        violations.extend(_verify_presence(ir))
        if ir.program is not None and ir.lowering is not None:
            violations.extend(_verify_lowering_header(ir, ctx.robot_spec))
            for trajectory in ir.lowering.trajectories:
                violations.extend(_verify_trajectory(trajectory, ir.execution.dof))
            for solution in ir.lowering.ik_solutions:
                violations.extend(_verify_solution(solution, ir.execution.dof))
            violations.extend(_verify_summaries(ir))
        if ir.constraints.payload_kg is not None and ir.constraints.payload_kg < 0:
            violations.append(f"constraints.payload_kg is negative ({ir.constraints.payload_kg})")
        unknown_checks = set(ir.verification.safety_checks) - _KNOWN_SAFETY_CHECKS
        if unknown_checks:
            violations.append(
                f"verification.safety_checks names unknown check(s): {sorted(unknown_checks)}"
            )
        diagnostics = _verification_diagnostic(ir, violations)
        return PassResult(
            ir=ir, diagnostics=diagnostics, metrics={
                "violations": float(len(violations)),
                "task_count": float(structure["task_count"]),
            }
        )


class CapabilityPass(CompilerPass):
    """Thin wrapper around ir/diagnostics.py::check_required_capabilities() -- same
    diagnostics, same codes (RW102, RW201), now run through the Pass Manager."""

    name = "CapabilityPass"

    def run(self, ctx: PassContext) -> PassResult:
        structure = ctx.analyses.get("roboir.structure", ctx)
        diagnostics = check_required_capabilities(ctx.ir, ctx.robot_spec)
        return PassResult(
            ir=ctx.ir, diagnostics=diagnostics, metrics={
                "diagnostic_count": float(len(diagnostics)),
                "object_count": float(structure["object_count"]),
            }
        )


class SafetyPass(CompilerPass):
    """Thin wrapper around ir/safety.py::check_safety() -- same diagnostics, same
    codes (RW301-RW306), now run through the Pass Manager."""

    name = "SafetyPass"

    def run(self, ctx: PassContext) -> PassResult:
        structure = ctx.analyses.get("roboir.structure", ctx)
        diagnostics = check_safety(ctx.ir, ctx.robot_spec)
        return PassResult(
            ir=ctx.ir, diagnostics=diagnostics, metrics={
                "diagnostic_count": float(len(diagnostics)),
                "trajectory_count": float(structure["trajectory_count"]),
            }
        )
