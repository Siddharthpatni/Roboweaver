"""
Optimization engine: a real cost model plus a real Pareto (dominated-solution) filter
-- docs/COMPILER_ROADMAP.md v2 vision, item 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.ir.safety import compute_manipulability
from roboweaver.types import CompiledSkill, estimate_cycle_time

if TYPE_CHECKING:
    from roboweaver.ir.schema import RoboIR
    from roboweaver.runtime.memory import ExecutionMemoryStore


@dataclass(frozen=True)
class CompiledSkillCost:
    """Every field is real, computed from data already produced by the compile
    pipeline -- nothing estimated beyond what's already there.
    `historical_success_rate` stays None (never a fabricated number) unless a real
    ExecutionMemoryStore (item 6) has real recorded outcomes for this action/robot."""

    estimated_cycle_time_s: float
    payload_margin_kg: float
    total_joint_travel_rad: float
    manipulability_margin: float
    historical_success_rate: float | None


def compute_cost(
    skill: CompiledSkill, ir: "RoboIR", robot_spec: RobotSpec,
    memory: "ExecutionMemoryStore | None" = None,
) -> CompiledSkillCost:
    cycle_time = estimate_cycle_time(skill)

    payload_margin = robot_spec.payload_capacity_kg - (ir.constraints.payload_kg or 0.0)

    total_travel = 0.0
    for seg in skill.motion_plan.trajectories.values():
        total_travel += sum(abs(b - a) for a, b in zip(seg.start_pose, seg.end_pose))

    manipulabilities = [
        compute_manipulability(robot_spec, ik.joint_angles)
        for ik in skill.motion_plan.ik_results.values()
        if ik.success
    ]
    # Worst-case (minimum) manipulability across the plan's solved poses -- the
    # binding constraint for how close the plan comes to a singularity anywhere.
    manipulability_margin = min(manipulabilities) if manipulabilities else 0.0

    historical_success_rate = memory.success_rate(ir.action, robot_spec.id) if memory is not None else None

    return CompiledSkillCost(
        estimated_cycle_time_s=round(cycle_time, 4),
        payload_margin_kg=round(payload_margin, 4),
        total_joint_travel_rad=round(total_travel, 4),
        manipulability_margin=round(manipulability_margin, 6),
        historical_success_rate=historical_success_rate,
    )


def _objective_vector(cost: CompiledSkillCost) -> tuple[float, float, float, float]:
    """Every entry oriented so "higher is better" -- time/travel are negated."""
    return (
        -cost.estimated_cycle_time_s,
        cost.payload_margin_kg,
        -cost.total_joint_travel_rad,
        cost.manipulability_margin,
    )


def _dominates(a: CompiledSkillCost, b: CompiledSkillCost) -> bool:
    """A dominates B if A is at least as good on every objective and strictly
    better on at least one -- the standard Pareto-dominance definition."""
    a_vals, b_vals = _objective_vector(a), _objective_vector(b)
    at_least_as_good = all(x >= y for x, y in zip(a_vals, b_vals))
    strictly_better = any(x > y for x, y in zip(a_vals, b_vals))
    return at_least_as_good and strictly_better


def pareto_front(costs: dict[str, CompiledSkillCost]) -> list[str]:
    """Real dominated-solution filter over a discrete set of robots: ids not
    dominated by any other in the set. Explicitly a simple multi-objective filter
    over a fixed candidate set, not a continuous Pareto-front solver."""
    ids = list(costs.keys())
    return [
        rid for rid in ids
        if not any(_dominates(costs[other], costs[rid]) for other in ids if other != rid)
    ]


_DEFAULT_WEIGHTS: dict[str, float] = {"time": 0.25, "payload": 0.25, "travel": 0.25, "manipulability": 0.25}


def _weighted_score(cost: CompiledSkillCost, weights: dict[str, float]) -> float:
    return (
        -weights.get("time", 0.0) * cost.estimated_cycle_time_s
        + weights.get("payload", 0.0) * cost.payload_margin_kg
        - weights.get("travel", 0.0) * cost.total_joint_travel_rad
        + weights.get("manipulability", 0.0) * cost.manipulability_margin
    )


@dataclass
class RobotComparison:
    ranked: list[tuple[str, float, CompiledSkillCost]]
    pareto_optimal: list[str]
    skipped: dict[str, str] = field(default_factory=dict)  # robot_id -> why it couldn't be compiled


def compare_robots(
    instruction: str,
    robot_ids: list[str],
    weights: dict[str, float] | None = None,
    memory: "ExecutionMemoryStore | None" = None,
) -> RobotComparison:
    """Compiles the same instruction across every robot, computes each one's real
    cost, and returns both a weighted ranking (default equal weights -- a simple
    weighted-sum comparison, not a Pareto-front solver with a continuous frontier)
    and the real Pareto-optimal subset. A robot that genuinely can't compile this
    instruction (e.g. a missing declared capability) is reported in `skipped` with
    the real blocking reason, not silently dropped or faked into the ranking."""
    from roboweaver.compiler import SkillCompiler
    from roboweaver.ir import SkillCompilationError

    weights = weights or _DEFAULT_WEIGHTS
    costs: dict[str, CompiledSkillCost] = {}
    skipped: dict[str, str] = {}

    for robot_id in robot_ids:
        compiler = SkillCompiler(target_robot=robot_id)
        try:
            result = compiler.compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            skipped[robot_id] = "; ".join(d.message for d in exc.diagnostics)
            continue
        costs[robot_id] = compute_cost(result.skill, result.ir, compiler.robot_spec, memory=memory)

    scored = [(rid, _weighted_score(costs[rid], weights), costs[rid]) for rid in costs]
    scored.sort(key=lambda t: t[1], reverse=True)

    return RobotComparison(ranked=scored, pareto_optimal=pareto_front(costs), skipped=skipped)
