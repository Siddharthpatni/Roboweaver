"""
Safety Verification — the compiler's Safety pass, run inside compile_with_diagnostics()
right after the Compiler Debugger's capability check (ir/diagnostics.py) and before a
CompilationResult is returned.

RoboIR already declares its intent to run these checks
(VerificationSpec.safety_checks == ["reach", "floor", "payload", "joint_limits"], see
ir/schema.py) but until this module nothing actually ran them: hardware/safety_guard.py's
WorkspaceSafetyGuard existed, was unit-tested, and was wired into the cross-embodiment
retargeter (fleet/retargeter.py) -- but never into the main compile path. That's the same
"real module, never connected" gap as TelemetryRecorder/RecoveryEngine before they were
wired into SkillRuntime.execute() (see docs/REDESIGN.md Sec 11). This module closes it for
compile-time checks, and adds two checks nothing in the codebase computed before:
reachability (IKResult.success was computed by _plan_motion and silently discarded) and
manipulability (a real finite-difference Jacobian at the solved configuration, computed
the same way NDOFIKSolver computes its Jacobian internally).

What is NOT checked here, and why -- see docs/COMPILER_ARCHITECTURE.md Section 1 for the
full accounting:
  - Self-collision and continuous swept-volume proof remain out of scope. When a
    typed Scene is supplied, the final collision pass checks sampled link capsules or
    an inflated mobile-base footprint against sphere/AABB environment obstacles.
  - Torque limits: JointSpec.max_effort is real, declared data, but nothing in RoboWeaver
    computes required torque (that needs a dynamics/mass model RoboWeaver doesn't have) --
    checking a real limit against a fabricated "required torque" would be exactly the kind
    of fake result this project explicitly refuses to produce.
  - Acceleration limits: JointSpec has no declared max_acceleration field at all.
  - Human-safety zones are not inferred from generic obstacles. E-stop/watchdog state
    is required by the guarded HIL runner, not proven by compile-time motion checks.
"""

from __future__ import annotations

import math
from typing import Sequence

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.hardware.safety_guard import WorkspaceSafetyGuard
from roboweaver.ir.adapters import compiled_skill_from_ir
from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.ir.schema import RoboIR
from roboweaver.math3d import Vec3
from roboweaver.types import CompiledSkill

# Yoshikawa manipulability index (sqrt(det(J J^T))) below this is flagged as
# operating close to a kinematic singularity. Not a robot-specific calibrated
# value -- a conservative general-purpose threshold, stated as such in the
# diagnostic so it reads as a heuristic, not a certified safety bound.
_MANIPULABILITY_WARN_THRESHOLD = 0.02
_JACOBIAN_EPS = 1e-5


def check_safety(ir: RoboIR, robot_spec: RobotSpec) -> list[CompilerDiagnostic]:
    """Verify complete RoboIR against the selected robot's declared limits.

    The temporary ``CompiledSkill`` view is reconstructed exclusively from RoboIR
    so diagnostics, simulation, deployment, and code generation all inspect the
    same immutable compiler output. Nothing here can observe stale front-end state.
    """
    skill = compiled_skill_from_ir(ir)
    diagnostics: list[CompilerDiagnostic] = []
    guard = WorkspaceSafetyGuard(robot_spec)

    diagnostics.extend(_check_reachability(skill))
    diagnostics.extend(_check_workspace_and_floor(skill, guard))
    diagnostics.extend(_check_joint_limits(skill, robot_spec, guard))
    diagnostics.extend(_check_payload(ir, guard))
    diagnostics.extend(_check_velocity_limits(skill, robot_spec))
    diagnostics.extend(_check_manipulability(skill, robot_spec))
    return diagnostics


def _check_reachability(skill: CompiledSkill) -> list[CompilerDiagnostic]:
    out = []
    for name, ik in skill.motion_plan.ik_results.items():
        if not ik.success:
            out.append(
                CompilerDiagnostic(
                    code="RW301",
                    severity="error",
                    message=f"IK solve for '{name}' pose did not converge (residual {ik.residual:.4f}m).",
                    reason=(
                        "NDOFIKSolver reported success=False for this target -- the damped "
                        "pseudoinverse solve did not reach the requested tolerance within its "
                        "iteration budget, meaning the target is likely unreachable or requires "
                        "a redundant-arm configuration this seed didn't find."
                    ),
                    required_capability=None,
                    fixes=[
                        "Move the target closer to the robot's declared workspace.",
                        "Retry with a different IK seed (current seed: zero configuration).",
                        "Increase NDOFIKSolver max_iter / relax tol for this skill.",
                    ],
                )
            )
    return out


def _check_workspace_and_floor(skill: CompiledSkill, guard: WorkspaceSafetyGuard) -> list[CompilerDiagnostic]:
    out = []
    for name, ik in skill.motion_plan.ik_results.items():
        pos = Vec3(*ik.target_pos)
        result = guard.validate_pose(pos)
        if not result.is_safe:
            out.append(
                CompilerDiagnostic(
                    code="RW305",
                    severity="error",
                    message=f"Target pose '{name}' is outside the declared safe workspace.",
                    reason="; ".join(result.violations),
                    required_capability=None,
                    fixes=[
                        "Move the target within the robot's declared max_reach_m and above the floor plane.",
                        "Select a robot backend with a larger workspace envelope.",
                    ],
                )
            )
    return out


def _check_joint_limits(
    skill: CompiledSkill, robot_spec: RobotSpec, guard: WorkspaceSafetyGuard
) -> list[CompilerDiagnostic]:
    # Every configuration the compiler actually produced: each trajectory's real
    # start/end poses (which is where the motion planner's home-seed clamping in
    # compiler.py._plan_motion gets checked) plus the solved IK targets. Checking
    # what was actually planned, rather than guessing a synthetic "home" independently
    # of the motion planner, is what closed the RW302/home-seed mismatch this pass
    # first caught (compiler.py now clamps its zero-seed into each joint's declared
    # range; duplicating that guess here would just drift out of sync with it again).
    out = []
    configs: dict[str, Sequence[float]] = {}
    for seg_name, seg in skill.motion_plan.trajectories.items():
        configs[f"{seg_name} (start)"] = seg.start_pose
        configs[f"{seg_name} (end)"] = seg.end_pose
    configs.update({name: ik.joint_angles for name, ik in skill.motion_plan.ik_results.items()})

    for name, q in configs.items():
        result = guard.validate_joint_limits(q)
        if not result.is_safe:
            out.append(
                CompilerDiagnostic(
                    code="RW302",
                    severity="error",
                    message=f"Configuration '{name}' violates {robot_spec.name}'s declared joint limits.",
                    reason="; ".join(result.violations),
                    required_capability=None,
                    fixes=[
                        "Re-plan this pose so every joint stays within RobotSpec.get_joint_limits().",
                        "Select a robot backend whose joint ranges cover this configuration.",
                    ],
                )
            )
    return out


def _check_payload(ir: RoboIR, guard: WorkspaceSafetyGuard) -> list[CompilerDiagnostic]:
    if ir.constraints.payload_kg is None:
        return []
    result = guard.validate_payload(ir.constraints.payload_kg)
    if result.is_safe:
        return []
    return [
        CompilerDiagnostic(
            code="RW303",
            severity="error",
            message=f"Skill '{ir.skill_id}' declares a payload the target robot cannot carry.",
            reason="; ".join(result.violations),
            required_capability=None,
            fixes=[
                "Reduce the declared payload_kg constraint.",
                "Select a robot backend with sufficient payload_capacity_kg.",
            ],
        )
    ]


def _check_velocity_limits(skill: CompiledSkill, robot_spec: RobotSpec) -> list[CompilerDiagnostic]:
    """Finite-difference joint velocity between consecutive waypoints, assuming
    uniform time-stepping across the segment duration -- an approximation stated
    as such, not a claim of exact velocity-profile verification."""
    out = []
    max_vels = robot_spec.get_max_velocities()

    for name, seg in skill.motion_plan.trajectories.items():
        n = len(seg.waypoints)
        if n < 2 or seg.duration <= 0:
            continue
        dt = seg.duration / (n - 1)

        worst_joint = None
        worst_ratio = 1.0
        for i in range(n - 1):
            wp_a, wp_b = seg.waypoints[i], seg.waypoints[i + 1]
            for j in range(min(len(wp_a), len(wp_b), robot_spec.dof)):
                vel = abs(wp_b[j] - wp_a[j]) / dt
                limit = max_vels[j]
                if limit > 0:
                    ratio = vel / limit
                    if ratio > worst_ratio:
                        worst_ratio = ratio
                        worst_joint = robot_spec.joints[j].name

        if worst_joint is not None:
            out.append(
                CompilerDiagnostic(
                    code="RW304",
                    severity="error",
                    message=f"Trajectory '{name}' exceeds {worst_joint}'s declared max_velocity.",
                    reason=(
                        f"Finite-difference velocity over this segment's {n} waypoints "
                        f"(assuming uniform {dt * 1000:.1f}ms steps across its {seg.duration:.2f}s "
                        f"duration) peaks at {worst_ratio * 100:.0f}% of {worst_joint}'s max_velocity."
                    ),
                    required_capability=None,
                    fixes=[
                        "Increase this segment's planned duration.",
                        "Reduce the distance covered by this segment.",
                    ],
                )
            )
    return out


def compute_manipulability(robot_spec: RobotSpec, q: Sequence[float]) -> float:
    """Yoshikawa manipulability index at configuration `q`, from a real
    finite-difference positional Jacobian -- the same construction NDOFIKSolver uses
    internally. Standalone (not private to _check_manipulability) so
    optimize/cost_model.py (docs/COMPILER_ROADMAP.md v2 vision, item 8) can reuse
    the exact same math instead of a second, drifting copy."""
    from roboweaver.hardware.kinematics_ndof import forward_kinematics_ndof

    q = list(q)
    n = robot_spec.dof
    base_pos = forward_kinematics_ndof(robot_spec, q).pos

    jac_rows = [[0.0] * n for _ in range(3)]
    for j in range(n):
        q_plus = list(q)
        q_plus[j] += _JACOBIAN_EPS
        p_plus = forward_kinematics_ndof(robot_spec, q_plus).pos
        jac_rows[0][j] = (p_plus.x - base_pos.x) / _JACOBIAN_EPS
        jac_rows[1][j] = (p_plus.y - base_pos.y) / _JACOBIAN_EPS
        jac_rows[2][j] = (p_plus.z - base_pos.z) / _JACOBIAN_EPS

    # det(J J^T) for a 3xN Jacobian via the Gram matrix -- avoids needing a
    # general NxN determinant routine for redundant (N>3) arms.
    gram = [[sum(jac_rows[r][k] * jac_rows[c][k] for k in range(n)) for c in range(3)] for r in range(3)]
    det = (
        gram[0][0] * (gram[1][1] * gram[2][2] - gram[1][2] * gram[2][1])
        - gram[0][1] * (gram[1][0] * gram[2][2] - gram[1][2] * gram[2][0])
        + gram[0][2] * (gram[1][0] * gram[2][1] - gram[1][1] * gram[2][0])
    )
    return math.sqrt(max(det, 0.0))


def _check_manipulability(skill: CompiledSkill, robot_spec: RobotSpec) -> list[CompilerDiagnostic]:
    """Yoshikawa manipulability index at each solved IK configuration, recomputed
    here at the final solved configuration rather than during the solve."""
    out = []
    for name, ik in skill.motion_plan.ik_results.items():
        if not ik.success:
            continue
        manipulability = compute_manipulability(robot_spec, ik.joint_angles)

        if manipulability < _MANIPULABILITY_WARN_THRESHOLD:
            out.append(
                CompilerDiagnostic(
                    code="RW306",
                    severity="warning",
                    message=f"Configuration '{name}' is close to a kinematic singularity.",
                    reason=(
                        f"Yoshikawa manipulability index {manipulability:.4f} at this configuration "
                        f"is below the {_MANIPULABILITY_WARN_THRESHOLD} heuristic threshold -- small "
                        "Cartesian motions near this pose require large joint velocities."
                    ),
                    required_capability=None,
                    fixes=[
                        "Re-plan this pose away from full extension or joint alignment.",
                        "Add a nullspace-optimization objective that biases away from low-manipulability configurations.",
                    ],
                )
            )
    return out
