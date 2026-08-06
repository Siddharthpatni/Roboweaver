"""
AI-Powered Recovery Advisor — uses a local Ollama model to reason about runtime
failures and suggest targeted fixes, beyond what the rule-based RecoveryEngine
(runtime/recovery.py) provides.

Additive: the rule-based RecoveryEngine is always consulted first and always
produces a result. The AI advisor adds a richer, context-aware narrative on top
— when Ollama is unavailable, the rule-based plan is returned as-is with a
stated reason why the AI layer couldn't contribute.

This module never executes a recovery action — it recommends, and the caller
(runtime/engine.py or the dashboard API) decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roboweaver.nlu.ollama_manager import OllamaManager, get_manager


@dataclass
class AIRecoveryAdvice:
    """AI-enriched recovery advice. `ai_explanation` is None when Ollama was
    unavailable — `error` states why, and `rule_based_action`/`rule_based_reason`
    always carry the deterministic RecoveryEngine's output regardless."""
    rule_based_action: str
    rule_based_reason: str
    ai_explanation: str | None = None
    ai_suggested_params: dict[str, Any] | None = None
    ai_root_cause: str | None = None
    fix_description: str | None = None
    confidence: float | None = None
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


_RECOVERY_SYSTEM = """You are a robotics failure analysis expert working with the RoboWeaver \
compiler infrastructure. You analyze runtime failures from robot skill execution and provide \
actionable root cause analysis and recovery guidance.

Rules:
- Be precise about mechanical, control, and planning causes.
- Suggest concrete parameter changes (e.g., "increase approach_height from 0.12 to 0.18").
- Never suggest actions outside the robot's real capabilities.
- Reference specific RoboWeaver diagnostic codes (RW1xx-RW6xx) when relevant.
- Keep root cause analysis under 100 words, recovery guidance under 200 words.
"""

_RECOVERY_TEMPLATE = """A robot skill execution experienced a failure. Analyze the root cause \
and suggest recovery actions.

**Failure Mode:** {failure_mode}
**Rule-Based Recovery:** {rule_action} — {rule_reason}
**Robot:** {robot_id} ({dof}-DOF, {gripper_type} gripper)
**Skill Action:** {action}
**Target Object:** {object_name}
**Retry Count:** {retry_count}

**Additional Context:**
{context_details}

Provide:
1. **Root Cause** (1-2 sentences): What most likely caused this failure?
2. **Recovery Guidance** (2-4 bullet points): What specific steps should be taken?
3. **Parameter Adjustments** (if applicable): What numerical parameter changes would help?
4. **Confidence**: A calibrated number from 0.0 to 1.0 for this diagnosis.
5. **Prevention** (1 sentence): How to prevent this in future compilations?"""


class AIRecoveryAdvisor:
    """Enriches rule-based recovery plans with LLM-generated root cause analysis."""

    def __init__(self, manager: OllamaManager | None = None):
        self.manager = manager or get_manager()

    def advise(
        self,
        failure_mode: str,
        rule_based_action: str,
        rule_based_reason: str,
        robot_id: str = "unknown",
        robot_spec: dict[str, Any] | None = None,
        skill_context: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> AIRecoveryAdvice:
        """Generate AI-enriched recovery advice for a runtime failure.

        The rule-based action and reason are always passed through — this method
        adds AI analysis on top, never replaces it.
        """
        spec = robot_spec or {}
        ctx = skill_context or {}

        context_lines = []
        if ctx.get("action"):
            context_lines.append(f"- Skill action: {ctx['action']}")
        if ctx.get("object_name"):
            context_lines.append(f"- Target object: {ctx['object_name']}")
        if ctx.get("cycle_time"):
            context_lines.append(f"- Cycle time: {ctx['cycle_time']}s")
        if ctx.get("joint_limits_violated"):
            context_lines.append("- Joint limits were violated during execution")
        if ctx.get("grasp_force"):
            context_lines.append(f"- Grasp force: {ctx['grasp_force']}N")
        if ctx.get("error_message"):
            context_lines.append(f"- Error: {ctx['error_message']}")
        if ctx.get("diagnostic_code"):
            context_lines.append(f"- Compiler diagnostic: {ctx['diagnostic_code']}")

        context_details = "\n".join(context_lines) or "  (no additional context available)"

        prompt = _RECOVERY_TEMPLATE.format(
            failure_mode=failure_mode,
            rule_action=rule_based_action,
            rule_reason=rule_based_reason,
            robot_id=robot_id,
            dof=spec.get("dof", "?"),
            gripper_type=spec.get("gripper_type", "unknown"),
            action=ctx.get("action", "?"),
            object_name=ctx.get("object_name", "?"),
            retry_count=retry_count,
            context_details=context_details,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="recovery",
            system=_RECOVERY_SYSTEM,
            temperature=0.2,
        )

        if resp.text is None:
            return AIRecoveryAdvice(
                rule_based_action=rule_based_action,
                rule_based_reason=rule_based_reason,
                error=resp.error,
                model=resp.model,
                latency_s=resp.latency_s,
            )

        # Parse the AI response for structured sections
        text = resp.text
        root_cause = _extract_section(text, "Root Cause")
        recovery_guidance = _extract_section(text, "Recovery Guidance")
        params = _extract_section(text, "Parameter Adjustments")
        confidence = _extract_confidence(text)

        return AIRecoveryAdvice(
            rule_based_action=rule_based_action,
            rule_based_reason=rule_based_reason,
            ai_explanation=text,
            ai_root_cause=root_cause,
            fix_description=recovery_guidance,
            confidence=confidence,
            ai_suggested_params=_parse_parameter_changes(params) if params else None,
            model=resp.model,
            latency_s=resp.latency_s,
        )


def _extract_section(text: str, heading: str) -> str | None:
    """Extract a section from markdown-ish LLM output by heading name.
    Returns None if the section is not found."""
    import re
    pattern = rf"\*?\*?{re.escape(heading)}\*?\*?\s*(?:\(.*?\))?\s*:?\s*(.*?)(?=\n\*?\*?\d+\.|$|\n\*?\*?[A-Z])"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        return content if content else None
    return None


def _extract_confidence(text: str) -> float | None:
    """Read an explicitly stated confidence without inventing one."""
    import re
    match = re.search(r"confidence\*?\*?\s*:?\s*(\d+(?:\.\d+)?)\s*(%)?", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2) or value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _parse_parameter_changes(section: str) -> dict[str, Any]:
    """Keep the source text and extract unambiguous numeric old→new changes."""
    import re
    changes: dict[str, dict[str, float]] = {}
    pattern = re.compile(
        r"([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*"
        r"(-?\d+(?:\.\d+)?)\s*(?:->|→|\bto\b)\s*"
        r"(-?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for key, old, new in pattern.findall(section):
        changes[key] = {"from": float(old), "to": float(new)}
    return {"raw": section, "changes": changes}
