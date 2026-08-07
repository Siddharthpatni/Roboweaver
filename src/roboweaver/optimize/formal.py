"""
Bounded, discrete formal verification (docs/COMPILER_ROADMAP.md v2 vision, item 10).

Explicitly NOT a temporal-logic/SMT proof of a continuous-time property ("robot never
enters X") -- that needs a new solver dependency (e.g. z3-solver) and nonlinear real
arithmetic over trigonometric forward kinematics, genuinely research-grade work not
undertaken here without an explicit dependency decision. What's real and delivered:
checking every waypoint the compiler actually produced against a declared forbidden
joint-range zone -- plain arithmetic, no solver, no fabricated "proof" over states
that were never sampled.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.types import CompiledSkill


def _compiled_waypoint_dof(skill: CompiledSkill) -> int:
    return max(
        (
            len(waypoint)
            for segment in skill.motion_plan.trajectories.values()
            for waypoint in segment.waypoints
        ),
        default=0,
    )


def _invalid_range_reason(
    joint_idx: object,
    bounds: object,
    waypoint_dof: int,
) -> str | None:
    if isinstance(joint_idx, bool) or not isinstance(joint_idx, int) or joint_idx < 0:
        return f"joint index {joint_idx!r} is not a non-negative integer"
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
        return f"joint {joint_idx} does not declare exactly two bounds"

    lo, hi = bounds
    numeric = (int, float)
    if isinstance(lo, bool) or isinstance(hi, bool) or not isinstance(lo, numeric) or not isinstance(hi, numeric):
        return f"joint {joint_idx} bounds are not numeric"
    if not math.isfinite(float(lo)) or not math.isfinite(float(hi)):
        return f"joint {joint_idx} bounds are not finite"
    if lo > hi:
        return f"joint {joint_idx} lower bound {lo} exceeds upper bound {hi}"
    if waypoint_dof and joint_idx >= waypoint_dof:
        return f"joint index {joint_idx} is outside the compiled waypoint dimension {waypoint_dof}"
    return None


def check_forbidden_zone_violations(
    skill: CompiledSkill,
    forbidden_joint_ranges: Mapping[int, Sequence[float]] | None,
) -> list[CompilerDiagnostic]:
    """Real, bounded check: for every compiled waypoint, does the declared joint
    fall inside a declared forbidden range? Returns [] honestly if no zone is
    declared -- never fabricates a violation, or a "proof", where there's nothing
    real to check against. One diagnostic per (segment, joint) with any real
    violation -- summarized, not one per individual waypoint hit."""
    if not forbidden_joint_ranges:
        return []

    diagnostics: list[CompilerDiagnostic] = []
    waypoint_dof = _compiled_waypoint_dof(skill)
    valid_ranges: list[tuple[int, float, float]] = []
    for joint_idx, bounds in forbidden_joint_ranges.items():
        reason = _invalid_range_reason(joint_idx, bounds, waypoint_dof)
        if reason is not None:
            diagnostics.append(
                CompilerDiagnostic(
                    code="RW508",
                    severity="error",
                    message="Forbidden-zone declaration is invalid.",
                    reason=reason,
                    required_capability=None,
                    fixes=[
                        "Declare finite ordered bounds for a real zero-based joint index.",
                        "Validate the target RobotSpec before compilation.",
                    ],
                )
            )
            continue
        assert isinstance(joint_idx, int)
        assert isinstance(bounds, (tuple, list))
        valid_ranges.append((joint_idx, float(bounds[0]), float(bounds[1])))

    for seg_name, seg in skill.motion_plan.trajectories.items():
        for joint_idx, lo, hi in valid_ranges:
            violating_indices = [
                i for i, wp in enumerate(seg.waypoints)
                if joint_idx < len(wp) and lo <= wp[joint_idx] <= hi
            ]
            if violating_indices:
                diagnostics.append(
                    CompilerDiagnostic(
                        code="RW507",
                        severity="error",
                        message=(
                            f"Trajectory segment '{seg_name}' enters a declared "
                            f"forbidden zone on joint {joint_idx}."
                        ),
                        reason=(
                            f"{len(violating_indices)} of {len(seg.waypoints)} waypoints "
                            f"have joint[{joint_idx}] within the declared forbidden range "
                            f"[{lo}, {hi}] (first at waypoint {violating_indices[0]})."
                        ),
                        required_capability=None,
                        fixes=[
                            "Re-plan this segment to avoid the declared forbidden joint range.",
                            "Confirm the declared forbidden_joint_ranges are correct for this robot.",
                        ],
                    )
                )
    return diagnostics
