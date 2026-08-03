"""
Self-learning compiler mechanism (docs/COMPILER_ROADMAP.md v2 vision, item 12) --
real, but honestly untriggered today. This repo has zero accumulated real execution
history right now, so suggest_parameter_adjustments() returns None
("insufficient data") for everything until real usage (runtime/memory.py, item 6)
produces enough real records. This is the mechanism for self-improvement, not a
claim that self-improvement has already happened -- proven with real records
written by a test, not a fabricated "10,000 execution" history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from roboweaver.runtime.memory import ExecutionMemoryStore

_LOW_SUCCESS_RATE_THRESHOLD = 0.7
_FREQUENT_RECOVERY_FRACTION = 0.3
_FREQUENT_JOINT_LIMIT_FRACTION = 0.2


def suggest_parameter_adjustments(
    action: str, robot_id: str, memory: "ExecutionMemoryStore", min_samples: int = 5,
) -> list[str] | None:
    """Real suggestions computed from real recorded runs -- never fabricated.
    Returns None below `min_samples` real records for this (action, robot_id) pair.
    With this repo's current zero accumulated history, that's honestly what every
    caller gets today; it activates once real usage produces real data."""
    records = memory.query(action=action, robot_id=robot_id, limit=10_000)
    if len(records) < min_samples:
        return None

    suggestions: list[str] = []
    n = len(records)

    successes = sum(1 for r in records if (r.get("execution") or {}).get("success"))
    success_rate = successes / n
    if success_rate < _LOW_SUCCESS_RATE_THRESHOLD:
        suggestions.append(
            f"{action} on {robot_id} succeeded in only {successes}/{n} real recorded "
            f"runs ({success_rate:.0%}) -- below the {_LOW_SUCCESS_RATE_THRESHOLD:.0%} "
            f"threshold. Review the skill template or target pose for this action."
        )

    action_counts: dict[str, int] = {}
    for r in records:
        for attempt in (r.get("execution") or {}).get("recovery_attempts", []):
            recovery_action = attempt.get("action")
            if recovery_action:
                action_counts[recovery_action] = action_counts.get(recovery_action, 0) + 1
    for recovery_action, count in action_counts.items():
        fraction = count / n
        if fraction >= _FREQUENT_RECOVERY_FRACTION:
            suggestions.append(
                f"Recovery action '{recovery_action}' was needed in {count}/{n} real "
                f"recorded runs ({fraction:.0%}) -- consider tuning the default "
                f"grasp/approach parameters for {action} on {robot_id} instead of "
                f"relying on recovery every time."
            )

    joint_violations = sum(
        1 for r in records if not (r.get("execution") or {}).get("joint_limits_respected", True)
    )
    if joint_violations / n >= _FREQUENT_JOINT_LIMIT_FRACTION:
        suggestions.append(
            f"{joint_violations}/{n} real recorded runs violated joint limits -- "
            f"review this skill's trajectory duration/velocity bounds for {robot_id}."
        )

    return suggestions or None
