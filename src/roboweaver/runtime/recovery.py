"""
Failure Detector & Recovery Engine — provides automated recovery policies for runtime execution failures.

V2: Added TIMEOUT and PERCEPTION_FAILED failure modes, WIDEN_APPROACH recovery action,
and smarter grasp-failure escalation with approach-vector offsets.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Any


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
class RecoveryPlan:
    failure_mode: FailureMode
    recommended_action: RecoveryAction
    reason: str
    max_retries: int = 3
    offset_m: float = 0.0  # Suggested positional offset for retry strategies


class RecoveryEngine:
    """Evaluates runtime failures and produces actionable recovery plans.

    V2: Graduated escalation for grasp failures (retry → widen → offset → replan),
    new failure modes for timeout and perception, and configurable retry budgets.
    """

    def diagnose(self, failure_mode: FailureMode, context: dict[str, Any] | None = None) -> RecoveryPlan:
        ctx = context or {}
        retry_count = ctx.get("retry_count", 0)

        if failure_mode == FailureMode.GRASP_FAILED:
            if retry_count < 2:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.RETRY_GRASP,
                    reason=f"Grasp force threshold not met. Retrying (attempt {retry_count + 1}/5)...",
                    max_retries=5,
                )
            elif retry_count < 3:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.WIDEN_APPROACH,
                    reason="Retry failed twice. Widening approach vector by 20mm for better alignment.",
                    max_retries=5,
                    offset_m=0.02,
                )
            elif retry_count < 4:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.RETRY_WITH_OFFSET,
                    reason="Widened approach didn't help. Applying lateral offset of 15mm.",
                    max_retries=5,
                    offset_m=0.015,
                )
            elif retry_count < 5:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.SWITCH_GRASP_STRATEGY,
                    reason="Multiple approach strategies exhausted. Switching grasp type (e.g. precision → power).",
                    max_retries=5,
                )
            else:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.REPLAN_APPROACH,
                    reason="Max grasp retries exceeded. Full re-planning of approach trajectory required.",
                    max_retries=5,
                )

        elif failure_mode == FailureMode.JOINT_LIMIT_VIOLATED:
            return RecoveryPlan(
                failure_mode=FailureMode.JOINT_LIMIT_VIOLATED,
                recommended_action=RecoveryAction.FALLBACK_HOME,
                reason="Joint angle exceeded physical limit. Returning arm to safe home position.",
            )

        elif failure_mode == FailureMode.TIMEOUT:
            return RecoveryPlan(
                failure_mode=FailureMode.TIMEOUT,
                recommended_action=RecoveryAction.FALLBACK_HOME,
                reason="Execution timed out. Returning arm to home and reporting incomplete task.",
            )

        elif failure_mode == FailureMode.PERCEPTION_FAILED:
            return RecoveryPlan(
                failure_mode=FailureMode.PERCEPTION_FAILED,
                recommended_action=RecoveryAction.RETRY_WITH_OFFSET,
                reason="Object detection/localization failed. Retrying with assumed default pose.",
                offset_m=0.0,
            )

        elif failure_mode == FailureMode.TARGET_UNREACHABLE:
            return RecoveryPlan(
                failure_mode=FailureMode.TARGET_UNREACHABLE,
                recommended_action=RecoveryAction.REPLAN_APPROACH,
                reason="IK solver could not reach target. Replanning with alternative seed configuration.",
            )

        else:
            return RecoveryPlan(
                failure_mode=failure_mode,
                recommended_action=RecoveryAction.EMERGENCY_STOP,
                reason="Unrecoverable trajectory or collision error. Triggering E-STOP.",
            )
