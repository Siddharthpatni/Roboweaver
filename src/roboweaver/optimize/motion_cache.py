"""
Motion-plan memoization -- the pure numeric part of compiler.py::SkillCompiler._plan_motion
(3 IK solves, 3 min-jerk trajectory generations, 3 duration calculations), extracted so it
can be memoized per robot.

Every compile today plans against the same three fixed Cartesian poses (grasp/approach/
lift -- see _GRASP_TARGET etc. below) regardless of the actual object or instruction:
RoboWeaver has no perception system yet (ir/diagnostics.py's RW201 warning says so on
every pick/place compile), so there is no real per-object target pose to plan against.
That means this computation is, today, a pure function of robot_spec.id alone -- which is
exactly what makes memoizing it honest right now. This is a load-bearing assumption, not
an oversight: once perception derives a real per-object target pose, the cache key here
must include that pose, not just robot_spec.id, or this cache would silently serve a
stale plan for a different object's location.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from roboweaver.hardware.kinematics_ndof import NDOFIKSolver
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Vec3
from roboweaver.types import IKSolution

# The 3 fixed Cartesian targets every pick/place-shaped compile plans against today.
_GRASP_TARGET = Vec3(0.35, 0.0, 0.13)
_APPROACH_TARGET = Vec3(0.35, 0.0, 0.25)
_LIFT_TARGET = Vec3(0.35, 0.0, 0.31)

_MIN_JERK_PEAK_SLOPE = 1.875  # ds/dt at t=0.5 for s(t) = 10t^3 - 15t^4 + 6t^5
_DURATION_SAFETY_MARGIN = 1.1


def min_safe_duration(
    robot_spec: RobotSpec, start_q: Sequence[float], end_q: Sequence[float], default: float
) -> float:
    """Shortest min-jerk blend duration keeping every joint's peak velocity within its
    declared max_velocity. Moved verbatim from compiler.py::_min_safe_duration (same
    formula/margin) so WaypointDecimationPass (optimize/passes.py) can reuse the exact
    same velocity-limit math for stride selection instead of a second, drifting copy."""
    max_vels = robot_spec.get_max_velocities()
    required = default
    for j in range(min(len(start_q), len(end_q), len(max_vels))):
        if max_vels[j] <= 0:
            continue
        delta = abs(end_q[j] - start_q[j])
        needed = (_MIN_JERK_PEAK_SLOPE * delta / max_vels[j]) * _DURATION_SAFETY_MARGIN
        required = max(required, needed)
    return required


def generate_min_jerk_traj(start_q: list[float], end_q: list[float], steps: int = 50) -> list[list[float]]:
    """Moved verbatim from compiler.py::_generate_min_jerk_traj."""
    waypoints = []
    n = len(start_q)
    for i in range(steps + 1):
        t = i / steps
        s = 10 * (t ** 3) - 15 * (t ** 4) + 6 * (t ** 5)
        wp = [start_q[j] + s * (end_q[j] - start_q[j]) for j in range(n)]
        waypoints.append(wp)
    return waypoints


@dataclass(frozen=True)
class PickPlacePrimitives:
    """The reusable, robot-only-dependent numeric result of the 3-pose pick/place
    motion plan. Object-name labeling of trajectory dict keys happens in
    compiler.py::_plan_motion, not here -- this is the object-independent part."""

    ik_grasp: IKSolution
    ik_approach: IKSolution
    ik_lift: IKSolution
    home_q: list[float]
    traj_approach: list[list[float]]
    traj_grasp: list[list[float]]
    traj_lift: list[list[float]]
    dur_approach: float
    dur_grasp: float
    dur_lift: float


_cache: dict[str, PickPlacePrimitives] = {}
_hits = 0
_misses = 0


def cache_stats() -> dict[str, int]:
    return {"hits": _hits, "misses": _misses, "entries": len(_cache)}


def clear_cache() -> None:
    """Test-only escape hatch -- production callers never need to invalidate this
    cache within a process lifetime (see module docstring's fixed-target caveat)."""
    global _hits, _misses
    _cache.clear()
    _hits = 0
    _misses = 0


def compute_pick_place_primitives(robot_spec: RobotSpec) -> tuple[PickPlacePrimitives, bool]:
    """Get-or-compute, memoized by robot_spec.id. Returns (primitives, was_cache_hit)."""
    global _hits, _misses
    cached = _cache.get(robot_spec.id)
    if cached is not None:
        _hits += 1
        return cached, True

    _misses += 1
    solver = NDOFIKSolver(robot_spec)

    ok1, q_grasp, res1, iters1 = solver.solve(_GRASP_TARGET)
    ok2, q_approach, res2, iters2 = solver.solve(_APPROACH_TARGET)
    ok3, q_lift, res3, iters3 = solver.solve(_LIFT_TARGET)

    ik_grasp = IKSolution(joint_angles=q_grasp, residual=res1, iterations=iters1, success=ok1)
    ik_approach = IKSolution(joint_angles=q_approach, residual=res2, iterations=iters2, success=ok2)
    ik_lift = IKSolution(joint_angles=q_lift, residual=res3, iterations=iters3, success=ok3)

    # Same zero-configuration-isn't-always-reachable clamp as the original
    # compiler.py::_plan_motion (RW302 caught this the first time it ran for Franka).
    home_q = [
        max(j.lower_limit, min(j.upper_limit, 0.0)) for j in robot_spec.joints[: robot_spec.dof]
    ]

    dur_approach = min_safe_duration(robot_spec, home_q, q_approach, default=1.0)
    dur_grasp = min_safe_duration(robot_spec, q_approach, q_grasp, default=0.4)
    dur_lift = min_safe_duration(robot_spec, q_grasp, q_lift, default=0.5)

    traj_approach = generate_min_jerk_traj(home_q, q_approach, steps=100)
    traj_grasp = generate_min_jerk_traj(q_approach, q_grasp, steps=40)
    traj_lift = generate_min_jerk_traj(q_grasp, q_lift, steps=50)

    primitives = PickPlacePrimitives(
        ik_grasp=ik_grasp, ik_approach=ik_approach, ik_lift=ik_lift,
        home_q=home_q,
        traj_approach=traj_approach, traj_grasp=traj_grasp, traj_lift=traj_lift,
        dur_approach=dur_approach, dur_grasp=dur_grasp, dur_lift=dur_lift,
    )
    _cache[robot_spec.id] = primitives
    return primitives, False
