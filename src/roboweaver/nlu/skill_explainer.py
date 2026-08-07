"""
AI-Powered Skill Explanation Engine — takes a CompilationResult and produces
human-readable natural language explanations using a local Ollama model.

This is additive, never a replacement: every explanation is a companion to the
real, structured compilation output (RoboIR, diagnostics, pass traces). If
Ollama is unavailable, explain() returns a stated error — the compilation
itself is never affected.

Capabilities:
  * explain_compilation() — full pipeline narrative: what was understood, what
    was planned, what was verified, what the skill does.
  * explain_diagnostics() — translates RW-code diagnostics into actionable
    natural-language guidance.
  * explain_safety() — generates a safety narrative: why this skill is/isn't
    safe for this specific robot.
  * explain_diff() — plain-English summary of a cross-robot RoboIR diff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roboweaver.nlu.ollama_manager import OllamaManager, get_manager


@dataclass
class SkillExplanation:
    """Human-readable explanation of a compiled skill. `text` is None when the
    LLM was unavailable — `error` always states why."""
    text: str | None
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


_EXPLAIN_SYSTEM = """You are a robotics compiler assistant for RoboWeaver, an LLVM-like compiler \
infrastructure for robotics. You explain compiled robot skills in clear, concise language \
that a robotics engineer would find useful.

Rules:
- Be precise and technical but accessible.
- Reference specific pipeline stages, pass names, and diagnostic codes when relevant.
- Never fabricate information — only explain what the compilation data actually shows.
- Keep explanations under 300 words unless the compilation is exceptionally complex.
- Use bullet points for lists of diagnostics or passes.
"""

_EXPLAIN_COMPILATION_TEMPLATE = """Explain what this compiled robot skill does, step by step.

**Instruction:** "{instruction}"
**Target Robot:** {robot_id} ({dof}-DOF, {gripper_type} gripper, {payload_kg}kg payload)

**Parsed Intent:**
- Action: {action}
- Target Object: {object_name}
- Confidence: {confidence}

**Task Graph:** {task_count} tasks
{task_list}

**RoboIR Summary:**
- Required capabilities: {capabilities}
- Safety checks: {safety_checks}

**Diagnostics:** {diagnostic_count} ({error_count} errors, {warning_count} warnings)
{diagnostic_list}

{pass_trace}

Provide a clear, engineer-friendly explanation of:
1. What the skill will make the robot do
2. How confident the parser was and why
3. Any warnings or issues found during compilation
4. Whether this skill is ready for deployment"""

_EXPLAIN_DIAGNOSTIC_TEMPLATE = """Explain this RoboWeaver compiler diagnostic in plain English \
and suggest concrete fixes.

**Diagnostic Code:** {code}
**Severity:** {severity}
**Message:** {message}
**Reason:** {reason}
**Required Capability:** {capability}
**Suggested Fixes:** {fixes}
**Target Robot:** {robot_id}

Explain:
1. What this diagnostic means in practical terms
2. Why it was raised for this specific robot
3. Step-by-step instructions to fix it
4. Whether this blocks deployment or is just advisory"""

_EXPLAIN_SAFETY_TEMPLATE = """Analyze the safety profile of this compiled robot skill.

**Instruction:** "{instruction}"
**Robot:** {robot_id} ({dof}-DOF, payload {payload_kg}kg, reach {reach_m}m)
**Action:** {action}

**Safety Checks Passed:** {safety_checks}
**Collision Check:** {collision_check}
**Simulation Required:** {sim_required}

**Diagnostics:**
{diagnostic_list}

**Motion Plan:**
- Trajectory segments: {segment_count}
- Total cycle time: {cycle_time}s

Provide a safety assessment:
1. Is this skill safe for this robot? Why or why not?
2. What safety measures are in place?
3. What additional precautions should be taken?
4. Any unresolved safety concerns?"""

_EXPLAIN_DIFF_TEMPLATE = """Summarize the differences between compiling the same instruction \
for two different robots, in plain English.

**Instruction:** "{instruction}"
**Robot A:** {robot_a}
**Robot B:** {robot_b}

**Field Changes:**
{field_changes}

**Objects Added in B:** {objects_added}
**Objects Removed in B:** {objects_removed}
**Objects Changed:** {objects_changed}

Explain:
1. Why these differences exist (what makes the robots different)
2. Which robot is better suited for this task and why
3. Any compatibility concerns"""


class SkillExplainer:
    """Generates natural language explanations of compiled skills using a local
    Ollama model. Never modifies compilation output — read-only and additive."""

    def __init__(self, manager: OllamaManager | None = None):
        self.manager = manager or get_manager()

    def explain_compilation(
        self, result: dict[str, Any], robot_spec: dict[str, Any] | None = None
    ) -> SkillExplanation:
        """Explain a full compilation result (from /api/compile JSON)."""
        ir = result.get("ir", {})
        intent = result.get("intent", {})
        tasks = result.get("tasks", [])
        diagnostics = result.get("diagnostics", [])
        execution = ir.get("execution", {})

        task_list = "\n".join(
            f"  {i+1}. [{t.get('type', '?')}] {t.get('description', '?')}"
            for i, t in enumerate(tasks)
        )

        diagnostic_list = "\n".join(
            f"  - [{d.get('severity', '?').upper()}] {d.get('code', '?')}: {d.get('message', '?')}"
            for d in diagnostics
        ) or "  (none)"

        caps = ir.get("required_capabilities", {})
        capabilities = ", ".join(
            caps.get("perception", []) + caps.get("manipulation", []) + caps.get("sensing", [])
        ) or "(none)"

        verification = ir.get("verification", {})
        safety_checks = ", ".join(verification.get("safety_checks", [])) or "(none)"

        # Pass trace summary if available
        pass_trace = ""
        pipeline = result.get("pipeline")
        if pipeline:
            passes = pipeline.get("passes", [])
            pass_lines = "\n".join(
                f"  - {p.get('pass_name', '?')} "
                f"({'modified' if p.get('modified') else 'no change'}, "
                f"{p.get('timing_s', 0)*1000:.1f}ms, "
                f"{p.get('diagnostic_count', 0)} diagnostics)"
                for p in passes
            )
            pass_trace = f"**Pipeline Passes:**\n{pass_lines}"

        prompt = _EXPLAIN_COMPILATION_TEMPLATE.format(
            instruction=result.get("instruction", "?"),
            robot_id=execution.get("robot_id", result.get("robot", "?")),
            dof=execution.get("dof", "?"),
            gripper_type=robot_spec.get("gripper_type", "unknown") if robot_spec else "unknown",
            payload_kg=robot_spec.get("payload_capacity_kg", "?") if robot_spec else "?",
            action=intent.get("action", "?"),
            object_name=intent.get("object_name", "?"),
            confidence=intent.get("parameters", {}).get("confidence", "1.0"),
            task_count=len(tasks),
            task_list=task_list or "  (empty task graph)",
            capabilities=capabilities,
            safety_checks=safety_checks,
            diagnostic_count=len(diagnostics),
            error_count=sum(1 for d in diagnostics if d.get("severity") == "error"),
            warning_count=sum(1 for d in diagnostics if d.get("severity") == "warning"),
            diagnostic_list=diagnostic_list,
            pass_trace=pass_trace,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="explainer",
            system=_EXPLAIN_SYSTEM,
            temperature=0.2,
        )

        return SkillExplanation(
            text=resp.text,
            model=resp.model,
            latency_s=resp.latency_s,
            error=resp.error,
        )

    def explain_diagnostic(
        self, diagnostic: dict[str, Any], robot_id: str = "unknown"
    ) -> SkillExplanation:
        """Explain a single compiler diagnostic in plain English."""
        prompt = _EXPLAIN_DIAGNOSTIC_TEMPLATE.format(
            code=diagnostic.get("code", "?"),
            severity=diagnostic.get("severity", "?"),
            message=diagnostic.get("message", "?"),
            reason=diagnostic.get("reason", "?"),
            capability=diagnostic.get("required_capability") or "(none)",
            fixes=", ".join(diagnostic.get("fixes", [])) or "(no suggestions)",
            robot_id=robot_id,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="explainer",
            system=_EXPLAIN_SYSTEM,
            temperature=0.2,
        )

        return SkillExplanation(
            text=resp.text, model=resp.model,
            latency_s=resp.latency_s, error=resp.error,
        )

    def explain_safety(
        self, result: dict[str, Any], robot_spec: dict[str, Any] | None = None
    ) -> SkillExplanation:
        """Generate a safety narrative for a compiled skill."""
        ir = result.get("ir", {})
        intent = result.get("intent", {})
        diagnostics = result.get("diagnostics", [])
        execution = ir.get("execution", {})
        verification = ir.get("verification", {})

        diagnostic_list = "\n".join(
            f"  - [{d.get('severity', '?').upper()}] {d.get('code', '?')}: {d.get('message', '?')}"
            for d in diagnostics
        ) or "  (no diagnostics — clean compile)"

        prompt = _EXPLAIN_SAFETY_TEMPLATE.format(
            instruction=result.get("instruction", "?"),
            robot_id=execution.get("robot_id", result.get("robot", "?")),
            dof=execution.get("dof", "?"),
            payload_kg=robot_spec.get("payload_capacity_kg", "?") if robot_spec else "?",
            reach_m=robot_spec.get("max_reach_m", "?") if robot_spec else "?",
            action=intent.get("action", "?"),
            safety_checks=", ".join(verification.get("safety_checks", [])) or "(none)",
            collision_check=verification.get("collision_check", False),
            sim_required=verification.get("simulation_required", False),
            diagnostic_list=diagnostic_list,
            segment_count=len(result.get("tasks", [])),
            cycle_time="?",
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="explainer",
            system=_EXPLAIN_SYSTEM,
            temperature=0.2,
        )

        return SkillExplanation(
            text=resp.text, model=resp.model,
            latency_s=resp.latency_s, error=resp.error,
        )

    def explain_diff(self, diff: dict[str, Any]) -> SkillExplanation:
        """Summarize a cross-robot RoboIR diff in plain English."""
        field_changes = "\n".join(
            f"  - {k}: {v[0]} → {v[1]}" if isinstance(v, list) and len(v) == 2 else f"  - {k}: {v}"
            for k, v in diff.get("field_changes", {}).items()
        ) or "  (no field-level changes)"

        objects_added = ", ".join(
            o.get("name", o.get("id", "?")) for o in diff.get("objects_added", [])
        ) or "(none)"

        objects_removed = ", ".join(
            o.get("name", o.get("id", "?")) for o in diff.get("objects_removed", [])
        ) or "(none)"

        objects_changed = "\n".join(
            f"  - {c.get('before', {}).get('id', '?')}: changes in role/pose/class"
            for c in diff.get("objects_changed", [])
        ) or "  (none)"

        prompt = _EXPLAIN_DIFF_TEMPLATE.format(
            instruction=diff.get("instruction", "?"),
            robot_a=diff.get("from_robot", "?"),
            robot_b=diff.get("to_robot", "?"),
            field_changes=field_changes,
            objects_added=objects_added,
            objects_removed=objects_removed,
            objects_changed=objects_changed,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="explainer",
            system=_EXPLAIN_SYSTEM,
            temperature=0.3,
        )

        return SkillExplanation(
            text=resp.text, model=resp.model,
            latency_s=resp.latency_s, error=resp.error,
        )
