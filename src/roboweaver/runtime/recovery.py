"""
Failure Detector & Recovery Engine — automated recovery policies for runtime
execution failures.

v3 (docs/COMPILER_ROADMAP.md v2 vision, item 7 -- "failure intelligence"): replaces
the old hardcoded if/elif retry-count ladder with a scored decision over declared
RecoveryCandidate priors (probability/cost/safety -- authored engineering estimates,
documented as such, not learned data), optionally boosted by *real* historical
recovery outcomes when an ExecutionMemoryStore (runtime/memory.py, item 6) is
attached and has real records. `RecoveryPlan.used_historical_data` tells a caller
whether a decision came from real history or from priors -- never claims "learned"
when it's actually a prior. `diagnose()` is a thin, signature-preserving wrapper
around the new `plan()` so every existing caller (runtime/engine.py) is unaffected.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from roboweaver.runtime.memory import ExecutionMemoryStore


class FailureMode(Enum):
    GRASP_FAILED = "GRASP_FAILED"
    JOINT_LIMIT_VIOLATED = "JOINT_LIMIT_VIOLATED"
    COLLISION_DETECTED = "COLLISION_DETECTED"
    IK_TIMEOUT = "IK_TIMEOUT"
    TIMEOUT = "TIMEOUT"
    PERCEPTION_FAILED = "PERCEPTION_FAILED"
    TARGET_UNREACHABLE = "TARGET_UNREACHABLE"


class RecoveryAction(Enum):
    RETRY_GRASP = "RETRY_GRASP"
    WIDEN_APPROACH = "WIDEN_APPROACH"
    REPLAN_APPROACH = "REPLAN_APPROACH"
    FALLBACK_HOME = "FALLBACK_HOME"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RETRY_WITH_OFFSET = "RETRY_WITH_OFFSET"
    SWITCH_GRASP_STRATEGY = "SWITCH_GRASP_STRATEGY"


@dataclass
class RecoveryCandidate:
    """One candidate response to a failure, with declared (not learned) engineering
    priors. `score` is what plan() ranks candidates by; `estimated_success_probability`
    is replaced with a real historical rate when ExecutionMemoryStore has one."""

    action: RecoveryAction
    estimated_success_probability: float
    cost_s: float
    safety_score: float
    offset_m: float
    reason: str

    @property
    def score(self) -> float:
        return (self.estimated_success_probability * self.safety_score) / max(self.cost_s, 1e-6)


@dataclass
class RecoveryPlan:
    failure_mode: FailureMode
    recommended_action: RecoveryAction
    reason: str
    max_retries: int = 3
    offset_m: float = 0.0  # Suggested positional offset for retry strategies
    used_historical_data: bool = False


class RecoveryEngine:
    """Evaluates runtime failures and produces actionable recovery plans via a real
    scored decision over declared candidates -- see module docstring."""

    def __init__(self, memory: "ExecutionMemoryStore | None" = None):
        # Attaching a real ExecutionMemoryStore here lets diagnose() (the same
        # call runtime/engine.py has always made) automatically become
        # history-aware once real recovery outcomes accumulate -- no change to
        # diagnose()'s call sites required.
        self.memory = memory

    def candidates(self, failure_mode: FailureMode, context: dict[str, Any] | None = None) -> list[RecoveryCandidate]:
        """Declared engineering priors per failure mode -- explicitly authored
        estimates (mirroring the v2 ladder's implicit escalation ordering with
        explicit numbers), not learned data. Real historical data (see plan())
        is what actually earns the "not fabricated" label; these are the honest
        starting point before any history exists."""
        if failure_mode == FailureMode.GRASP_FAILED:
            return [
                RecoveryCandidate(
                    RecoveryAction.RETRY_GRASP, 0.55, 0.5, 1.0, 0.0,
                    "Grasp force threshold not met -- a bare retry recovers a real "
                    "fraction of transient contact-force misses.",
                ),
                RecoveryCandidate(
                    RecoveryAction.WIDEN_APPROACH, 0.5, 1.0, 0.9, 0.02,
                    "Widening the approach vector improves alignment when a bare "
                    "retry didn't help.",
                ),
                RecoveryCandidate(
                    RecoveryAction.RETRY_WITH_OFFSET, 0.45, 1.0, 0.9, 0.015,
                    "A lateral offset compensates for a systematic alignment miss.",
                ),
                RecoveryCandidate(
                    RecoveryAction.SWITCH_GRASP_STRATEGY, 0.4, 1.5, 0.8, 0.0,
                    "Switching grasp type (precision -> power) handles a "
                    "shape/friction mismatch.",
                ),
                RecoveryCandidate(
                    RecoveryAction.REPLAN_APPROACH, 0.35, 2.0, 0.7, 0.0,
                    "Full re-planning is the last resort once every targeted "
                    "correction failed.",
                ),
            ]
        if failure_mode == FailureMode.JOINT_LIMIT_VIOLATED:
            return [
                RecoveryCandidate(
                    RecoveryAction.FALLBACK_HOME, 0.9, 1.0, 1.0, 0.0,
                    "Joint angle exceeded a physical limit -- return to a "
                    "known-safe home configuration.",
                )
            ]
        if failure_mode == FailureMode.TIMEOUT:
            return [
                RecoveryCandidate(
                    RecoveryAction.FALLBACK_HOME, 0.9, 1.0, 1.0, 0.0,
                    "Execution timed out -- return to home and report incomplete.",
                )
            ]
        if failure_mode == FailureMode.PERCEPTION_FAILED:
            return [
                RecoveryCandidate(
                    RecoveryAction.RETRY_WITH_OFFSET, 0.4, 1.0, 0.8, 0.0,
                    "Object detection/localization failed -- retry with the "
                    "assumed default pose.",
                )
            ]
        if failure_mode == FailureMode.TARGET_UNREACHABLE:
            return [
                RecoveryCandidate(
                    RecoveryAction.REPLAN_APPROACH, 0.5, 2.0, 0.8, 0.0,
                    "IK solver could not reach target -- replan with an "
                    "alternative seed configuration.",
                )
            ]
        return [
            RecoveryCandidate(
                RecoveryAction.EMERGENCY_STOP, 1.0, 0.1, 1.0, 0.0,
                "Unrecoverable trajectory or collision error.",
            )
        ]

    def plan(
        self,
        failure_mode: FailureMode,
        context: dict[str, Any] | None = None,
        memory: "ExecutionMemoryStore | None" = None,
    ) -> RecoveryPlan:
        ctx = context or {}
        retry_count = ctx.get("retry_count", 0)
        cands = self.candidates(failure_mode, ctx)

        attempted = set(ctx.get("attempted_actions", set()))
        # Backward-compatible derivation: runtime/engine.py's long-standing contract
        # only ever passes retry_count, not an explicit attempted_actions set.
        # Treating the top `retry_count` scored candidates as already tried
        # reproduces graduated escalation from real declared scores instead of the
        # old hardcoded thresholds.
        if not attempted and retry_count > 0:
            ranked = sorted(cands, key=lambda c: c.score, reverse=True)
            attempted = {c.action for c in ranked[: min(retry_count, len(ranked))]}

        pool = [c for c in cands if c.action not in attempted] or cands

        used_historical_data = False
        active_memory = memory if memory is not None else self.memory
        if active_memory is not None:
            robot_id = ctx.get("robot_id", "unknown")
            boosted = []
            for c in pool:
                real_rate = active_memory.recovery_action_success_rate(
                    failure_mode.value, c.action.value, robot_id
                )
                if real_rate is not None:
                    used_historical_data = True
                    boosted.append(dataclasses.replace(c, estimated_success_probability=real_rate))
                else:
                    boosted.append(c)
            pool = boosted

        best = max(pool, key=lambda c: c.score)
        return RecoveryPlan(
            failure_mode=failure_mode,
            recommended_action=best.action,
            reason=best.reason,
            max_retries=5 if failure_mode == FailureMode.GRASP_FAILED else 3,
            offset_m=best.offset_m,
            used_historical_data=used_historical_data,
        )

    def diagnose(self, failure_mode: FailureMode, context: dict[str, Any] | None = None) -> RecoveryPlan:
        """Thin, signature-preserving wrapper around plan() -- every existing
        caller (runtime/engine.py's two call sites) is unaffected. Uses
        self.memory automatically if this engine was constructed with one."""
        return self.plan(failure_mode, context)
