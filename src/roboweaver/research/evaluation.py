"""Small reproducible evaluation harness with explicit, defensible metrics."""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import OptimizationLevel, SkillCompilationError
from roboweaver.runtime.validation import validate_in_simulation


@dataclass(frozen=True)
class EvaluationMetric:
    name: str
    passed: bool
    value: float | int | str | bool
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ResearchEvaluation:
    benchmark_version: str
    metrics: tuple[EvaluationMetric, ...]
    elapsed_s: float
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_version": self.benchmark_version,
            "passed": sum(metric.passed for metric in self.metrics),
            "total": len(self.metrics),
            "elapsed_s": round(self.elapsed_s, 4),
            "metrics": [asdict(metric) for metric in self.metrics],
            "limitations": list(self.limitations),
        }


def _ir_digest(result) -> str:
    payload = json.dumps(result.ir.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _waypoint_count(result) -> int:
    lowering = result.ir.lowering
    return sum(len(segment.waypoints) for segment in lowering.trajectories) if lowering else 0


def _determinism_metric() -> EvaluationMetric:
    digests = [
        _ir_digest(SkillCompiler("franka_panda").compile_with_diagnostics(
            "Pick up the red cube", verbose=False
        ))
        for _ in range(3)
    ]
    return EvaluationMetric(
        "determinism",
        len(set(digests)) == 1,
        len(set(digests)),
        {"runs": 3, "unique_ir_sha256": sorted(set(digests))},
    )


def _portability_metric() -> EvaluationMetric:
    targets = ["franka_panda", "ur5e", "kuka_iiwa"]
    result = SkillCompiler.compile_targets("Pick up the red cube", targets, verbose=False)
    accepted = sorted(result.results)
    return EvaluationMetric(
        "target_portability",
        accepted == sorted(targets) and not result.failures,
        len(accepted),
        {
            "source_sha256": result.source_digest,
            "requested_targets": targets,
            "accepted_targets": accepted,
            "rejected_targets": sorted(result.failures),
        },
    )


def _diagnostic_metric() -> EvaluationMetric:
    observed: list[str] = []
    try:
        SkillCompiler("temi").compile_with_diagnostics("Tighten the M8 bolt", verbose=False)
    except SkillCompilationError as exc:
        observed = [item.code for item in exc.diagnostics]
    expected = ["RW102"]
    precision = len(set(observed) & set(expected)) / len(observed) if observed else 0.0
    recall = len(set(observed) & set(expected)) / len(expected)
    return EvaluationMetric(
        "diagnostic_precision",
        observed == expected,
        round(precision, 4),
        {"expected": expected, "observed": observed, "precision": precision, "recall": recall},
    )


def _runtime_metric() -> EvaluationMetric:
    compiler = SkillCompiler("franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)
    execution = validate_in_simulation(result.ir, compiler.robot_spec)
    return EvaluationMetric(
        "runtime_correctness",
        execution.success and execution.joint_limits_respected and execution.height_gained > 0,
        round(execution.height_gained, 6),
        {
            "native_twin_success": execution.success,
            "joint_limits_respected": execution.joint_limits_respected,
            "height_gained_m": round(execution.height_gained, 6),
            "cycle_time_s": round(execution.cycle_time, 6),
        },
    )


def _planning_baseline_metric() -> EvaluationMetric:
    timings: dict[str, list[float]] = {"O0": [], "O1": []}
    waypoints: dict[str, list[int]] = {"O0": [], "O1": []}
    for name, level in (("O0", OptimizationLevel.O0), ("O1", OptimizationLevel.O1)):
        for _ in range(3):
            started = time.perf_counter()
            result = SkillCompiler("franka_panda").compile_with_diagnostics(
                "Pick up the red cube", verbose=False, optimization_level=level
            )
            timings[name].append(time.perf_counter() - started)
            waypoints[name].append(_waypoint_count(result))
    o0 = int(statistics.median(waypoints["O0"]))
    o1 = int(statistics.median(waypoints["O1"]))
    reduction = (o0 - o1) / o0 if o0 else 0.0
    return EvaluationMetric(
        "planning_performance",
        o1 <= o0,
        round(reduction, 4),
        {
            "baseline": "RoboWeaver O0",
            "candidate": "RoboWeaver O1",
            "runs_per_level": 3,
            "median_waypoints": {"O0": o0, "O1": o1},
            "median_compile_ms": {
                name: round(statistics.median(values) * 1000, 3) for name, values in timings.items()
            },
            "waypoint_reduction": round(reduction, 4),
        },
    )


def _compilation_success_metric() -> EvaluationMetric:
    cases = [
        ("franka_panda", "Pick up the red cube", True),
        ("turtlebot4", "Navigate to the loading dock", True),
        ("shadow_hand", "Grasp the small cylinder", True),
        ("temi", "Tighten the M8 bolt", False),
    ]
    outcomes: list[dict[str, Any]] = []
    correct = 0
    for robot, instruction, expected in cases:
        succeeded = True
        diagnostics: list[str] = []
        try:
            SkillCompiler(robot).compile_with_diagnostics(instruction, verbose=False)
        except SkillCompilationError as exc:
            succeeded = False
            diagnostics = [item.code for item in exc.diagnostics]
        correct += succeeded == expected
        outcomes.append({
            "robot": robot,
            "instruction": instruction,
            "expected_success": expected,
            "observed_success": succeeded,
            "diagnostics": diagnostics,
        })
    rate = correct / len(cases)
    return EvaluationMetric("compilation_success", correct == len(cases), round(rate, 4), {"cases": outcomes})


def run_research_evaluation() -> ResearchEvaluation:
    started = time.perf_counter()
    metrics = (
        _compilation_success_metric(),
        _diagnostic_metric(),
        _determinism_metric(),
        _portability_metric(),
        _runtime_metric(),
        _planning_baseline_metric(),
    )
    return ResearchEvaluation(
        "rw-research-v1",
        metrics,
        time.perf_counter() - started,
        (
            "Runtime correctness currently covers the modeled native PICK process, not Gazebo physics.",
            "The planning baseline is internal O0 versus O1, not yet MoveIt 2 or another external planner.",
            "This local run is evidence only for the current machine and commit; public CI evidence requires a push.",
        ),
    )
