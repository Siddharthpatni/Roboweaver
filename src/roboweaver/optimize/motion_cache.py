"""
Motion-plan memoization -- the pure numeric part of compiler.py::SkillCompiler._plan_motion,
generalized (gap-fix batch, item 1a) to solve one real IK-verified Cartesian target per
actual MOVE_TO task in the compiled skill's template, instead of a fixed 3-pose pick/place
plan -- closing RW502 (dangling MOVE_TO, optimize/passes.py) for every skill category, not
just pick-and-place.

Every compile still plans against a FIXED, assumed Cartesian path (no perception system
derives a real per-object target pose yet -- ir/diagnostics.py's RW201 warning says so on
every compile that needs one): a two-phase path descending from an "approach" height to a
"work" (contact/engage) height, then ascending from "work" to a "retract" height. Given N
real MOVE_TO tasks, N real Cartesian targets are interpolated along this fixed path and
each is independently IK-solved (warm-started from the previous solve) -- this generalizes
the exact same 3-pose logic this module always had, it isn't a new kind of fabrication.
Since the interpolation depends only on N (not on the skill's category), two categories
with the same MOVE_TO count get identical target poses today -- consistent with the
existing "assumed, not per-category-real" honesty (RW201), not a new inaccuracy.

Memoized per (robot_spec.id, n_targets): still honestly a pure function of these two
values today. This cache key must grow to include the real target pose once perception
exists, or it will silently serve a stale plan for a different object's location -- a
limitation already true (and already documented) before this generalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from roboweaver.hardware.kinematics_ndof import NDOFIKSolver
from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Vec3
from roboweaver.types import IKSolution

# The fixed, assumed two-phase Cartesian path every compile plans against today:
# descend from APPROACH to WORK, then ascend from WORK to RETRACT.
_APPROACH_TARGET = Vec3(0.35, 0.0, 0.25)
_WORK_TARGET = Vec3(0.35, 0.0, 0.13)
_RETRACT_TARGET = Vec3(0.35, 0.0, 0.31)

_MIN_JERK_PEAK_SLOPE = 1.875  # ds/dt at t=0.5 for s(t) = 10t^3 - 15t^4 + 6t^5
_DURATION_SAFETY_MARGIN = 1.1
_DEFAULT_SEGMENT_DURATION = 0.6
_DEFAULT_TRAJ_STEPS = 50


def min_safe_duration(
    robot_spec: RobotSpec, start_q: Sequence[float], end_q: Sequence[float], default: float
) -> float:
    """Shortest min-jerk blend duration keeping every joint's peak velocity within its
    declared max_velocity. Same formula/margin optimize/passes.py::WaypointDecimationPass
    reuses for stride selection -- one implementation, not a drifting second copy."""
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
    waypoints = []
    n = len(start_q)
    for i in range(steps + 1):
        t = i / steps
        s = 10 * (t ** 3) - 15 * (t ** 4) + 6 * (t ** 5)
        wp = [start_q[j] + s * (end_q[j] - start_q[j]) for j in range(n)]
        waypoints.append(wp)
    return waypoints


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return Vec3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t)


def _interpolate_targets(n: int) -> list[Vec3]:
    """N real Cartesian targets along the fixed descend-then-ascend path -- see
    module docstring. `n` must be >= 1."""
    if n == 1:
        return [_WORK_TARGET]
    n_descend = (n + 1) // 2
    n_ascend = n - n_descend
    targets = [_lerp(_APPROACH_TARGET, _WORK_TARGET, i / n_descend) for i in range(1, n_descend + 1)]
    targets += [_lerp(_WORK_TARGET, _RETRACT_TARGET, i / n_ascend) for i in range(1, n_ascend + 1)]
    return targets


@dataclass(frozen=True)
class MotionPrimitives:
    """N real, IK-solved target configurations and the N real min-jerk trajectory
    segments chaining home -> target_1 -> ... -> target_n. `start_configs[i]` is the
    configuration segment `i` starts from (home_q for i=0, else the previous target's
    solved config) -- object/task-description labeling happens in
    compiler.py::_plan_motion, not here."""

    home_q: list[float]
    ik_solutions: list[IKSolution]
    start_configs: list[list[float]]
    trajectory_waypoints: list[list[list[float]]]
    trajectory_durations: list[float]


_cache: dict[tuple[str, int], MotionPrimitives] = {}
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


def compute_motion_primitives(robot_spec: RobotSpec, n_targets: int) -> tuple[MotionPrimitives, bool]:
    """Get-or-compute, memoized by (robot_spec.id, n_targets) -- n_targets is the
    real number of MOVE_TO tasks in the compiled skill's template. Returns
    (primitives, was_cache_hit)."""
    if n_targets < 1:
        raise ValueError("compute_motion_primitives requires n_targets >= 1")

    global _hits, _misses
    key = (robot_spec.id, n_targets)
    cached = _cache.get(key)
    if cached is not None:
        _hits += 1
        return cached, True

    _misses += 1
    solver = NDOFIKSolver(robot_spec)

    # Same zero-configuration-isn't-always-reachable clamp as before (RW302 caught
    # this the first time it ran for Franka's panda_joint4).
    home_q = [
        max(j.lower_limit, min(j.upper_limit, 0.0)) for j in robot_spec.joints[: robot_spec.dof]
    ]

    targets = _interpolate_targets(n_targets)
    configs: list[list[float]] = [home_q]
    ik_solutions: list[IKSolution] = []
    for target in targets:
        # Warm-started from the previous solve -- real, standard IK practice for a
        # sequence of nearby targets, and a genuine improvement over always seeding
        # from the same fixed home/zero configuration.
        ok, q, res, iters = solver.solve(target, seed_q=configs[-1])
        ik_solutions.append(
            IKSolution(
                joint_angles=q, residual=res, iterations=iters, success=ok,
                target_pos=[target.x, target.y, target.z],
            )
        )
        configs.append(list(q))

    start_configs = configs[:-1]
    trajectory_waypoints: list[list[list[float]]] = []
    trajectory_durations: list[float] = []
    for i in range(n_targets):
        start_q, end_q = start_configs[i], ik_solutions[i].joint_angles
        duration = min_safe_duration(robot_spec, start_q, end_q, default=_DEFAULT_SEGMENT_DURATION)
        trajectory_waypoints.append(generate_min_jerk_traj(list(start_q), list(end_q), steps=_DEFAULT_TRAJ_STEPS))
        trajectory_durations.append(duration)

    primitives = MotionPrimitives(
        home_q=home_q, ik_solutions=ik_solutions, start_configs=start_configs,
        trajectory_waypoints=trajectory_waypoints, trajectory_durations=trajectory_durations,
    )
    _cache[key] = primitives
    return primitives, False
