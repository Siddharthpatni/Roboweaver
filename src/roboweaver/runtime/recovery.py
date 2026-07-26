"""
Failure Detector & Recovery Engine — provides automated recovery policies for runtime execution failures.
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


class RecoveryAction(Enum):
    RETRY_GRASP = "RETRY_GRASP"
    REPLAN_APPROACH = "REPLAN_APPROACH"
    FALLBACK_HOME = "FALLBACK_HOME"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class RecoveryPlan:
    failure_mode: FailureMode
    recommended_action: RecoveryAction
    reason: str
    max_retries: int = 3


class RecoveryEngine:
    """Evaluates runtime failures and produces actionable recovery plans."""

    def diagnose(self, failure_mode: FailureMode, context: dict[str, Any] | None = None) -> RecoveryPlan:
        ctx = context or {}
        retry_count = ctx.get("retry_count", 0)

        if failure_mode == FailureMode.GRASP_FAILED:
            if retry_count < 3:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.RETRY_GRASP,
                    reason=f"Grasp force threshold not met. Retrying (attempt {retry_count + 1}/3)...",
                )
            else:
                return RecoveryPlan(
                    failure_mode=FailureMode.GRASP_FAILED,
                    recommended_action=RecoveryAction.REPLAN_APPROACH,
                    reason="Max grasp retries exceeded. Replanning approach pose with offset.",
                )

        elif failure_mode == FailureMode.JOINT_LIMIT_VIOLATED:
            return RecoveryPlan(
                failure_mode=FailureMode.JOINT_LIMIT_VIOLATED,
                recommended_action=RecoveryAction.FALLBACK_HOME,
                reason="Joint angle exceeded physical limit. Returning arm to safe home position.",
            )

        else:
            return RecoveryPlan(
                failure_mode=failure_mode,
                recommended_action=RecoveryAction.EMERGENCY_STOP,
                reason="Unrecoverable trajectory or collision error. Triggering E-STOP.",
            )
