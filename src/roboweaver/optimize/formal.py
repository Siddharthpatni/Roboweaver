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

from roboweaver.ir.diagnostics import CompilerDiagnostic
from roboweaver.types import CompiledSkill


def check_forbidden_zone_violations(
    skill: CompiledSkill,
    forbidden_joint_ranges: dict[int, tuple[float, float]] | None,
) -> list[CompilerDiagnostic]:
    """Real, bounded check: for every compiled waypoint, does the declared joint
    fall inside a declared forbidden range? Returns [] honestly if no zone is
    declared -- never fabricates a violation, or a "proof", where there's nothing
    real to check against. One diagnostic per (segment, joint) with any real
    violation -- summarized, not one per individual waypoint hit."""
    if not forbidden_joint_ranges:
        return []

    diagnostics: list[CompilerDiagnostic] = []
    for seg_name, seg in skill.motion_plan.trajectories.items():
        for joint_idx, (lo, hi) in forbidden_joint_ranges.items():
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
