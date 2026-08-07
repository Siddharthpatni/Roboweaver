"""
AI-Enhanced Code Generation — uses a local Ollama model to review generated
ROS 2 / URScript code and add inline comments explaining what each block does.

Additive: the code generators (codegen/ros2_gen.py, codegen/urscript_gen.py)
produce valid output without this module. When Ollama is available, this module
adds a review pass that:

  * Annotates the generated code with inline comments explaining each section
  * Detects potential issues (unsafe velocity, missing error handling)
  * Suggests improvements

When Ollama is unavailable, returns the original code unchanged with a stated
error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from roboweaver.json_utils import loads_strict
from roboweaver.nlu.ollama_manager import OllamaManager, get_manager
from roboweaver.nlu.openrouter_manager import OpenRouterManager


@dataclass
class CodeReviewResult:
    """Result of an AI code review. `annotated_code` is the original code with
    inline comments added. `issues` lists potential problems found. Both are
    empty when the AI is unavailable."""
    original_code: str
    annotated_code: str | None = None
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


_REVIEW_SYSTEM = """You are a robotics code reviewer specializing in ROS 2 and robot controller \
code. You review auto-generated code for safety, correctness, and clarity.

Rules:
- Add inline comments (// or #) explaining what each functional block does.
- Flag any unsafe velocity or force commands.
- Flag missing error handling or timeout protection.
- Keep the original code structure intact — only add comments and mark issues.
- Do not rewrite the code, only annotate it.
- Mark issues with "// [ISSUE]" or "# [ISSUE]" prefixes.
- Mark suggestions with "// [SUGGEST]" or "# [SUGGEST]" prefixes.
- Output the full annotated code, nothing else.
"""

_ISSUES_SYSTEM = """You are a robotics safety code reviewer. Analyze only the supplied code,
do not invent runtime facts, and return exactly the requested JSON object with `issues` and
`suggestions` string arrays. Return empty arrays when no grounded finding exists."""

_REVIEW_TEMPLATE = """Review this auto-generated {language} robot code and add inline comments.

**Robot:** {robot_id} ({dof}-DOF)
**Skill Action:** {action}
**Target Object:** {object_name}

```{language_tag}
{code}
```

Add inline comments explaining each section, flag any safety concerns, and note \
improvement opportunities. Output the full annotated code."""

_ISSUES_TEMPLATE = """Analyze this auto-generated {language} robot code for potential issues.

**Robot:** {robot_id}
**Skill Action:** {action}

```{language_tag}
{code}
```

Output a JSON object:
{{
  "issues": ["<issue 1>", "<issue 2>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>"]
}}

Focus on: safety concerns, missing error handling, hardcoded values that should \
be parameters, velocity/force limits, and timeout protection."""


class AICodeReviewer:
    """Adds inline comments and safety reviews to generated robot code."""

    def __init__(self, manager: OllamaManager | OpenRouterManager | None = None):
        self.manager = manager or get_manager()

    def review_connection_python(
        self, code: str, robot_id: str, protocol: str, dof: int
    ) -> CodeReviewResult:
        """Annotate a deterministic connection probe in one bounded model call.

        General artifact review uses a second structured issue pass. Connection
        generation is interactive and must stay inside the dashboard proxy timeout,
        so issue markers remain inline and the authoritative source stays separate.
        """
        prompt = _REVIEW_TEMPLATE.format(
            language="Python robot connection adapter",
            language_tag="python",
            robot_id=robot_id,
            dof=dof,
            action=f"CONNECT_{protocol.upper()}",
            object_name="validated endpoint environment variable",
            code=code,
        )
        response = self.manager.generate(
            prompt=prompt,
            feature="codegen",
            system=_REVIEW_SYSTEM,
            temperature=0.1,
            timeout=55.0,
        )
        if response.text is None:
            return CodeReviewResult(
                original_code=code,
                error=response.error,
                model=response.model,
                latency_s=response.latency_s,
            )
        return CodeReviewResult(
            original_code=code,
            annotated_code=_extract_code_block(response.text) or response.text,
            model=response.model,
            latency_s=response.latency_s,
        )

    def review_ros2(
        self, code: str, robot_id: str = "unknown", action: str = "PICK",
        object_name: str = "object", dof: int = 7
    ) -> CodeReviewResult:
        """Review generated ROS 2 Python code."""
        return self._review(
            code=code, language="ROS 2 Python", language_tag="python",
            robot_id=robot_id, action=action, object_name=object_name, dof=dof,
        )

    def review_urscript(
        self, code: str, robot_id: str = "unknown", action: str = "PICK",
        object_name: str = "object", dof: int = 6
    ) -> CodeReviewResult:
        """Review generated URScript code."""
        return self._review(
            code=code, language="URScript", language_tag="urscript",
            robot_id=robot_id, action=action, object_name=object_name, dof=dof,
        )

    def _review(
        self, code: str, language: str, language_tag: str,
        robot_id: str, action: str, object_name: str, dof: int
    ) -> CodeReviewResult:
        """Internal review implementation."""
        # Step 1: Annotate the code
        annotate_prompt = _REVIEW_TEMPLATE.format(
            language=language, language_tag=language_tag,
            robot_id=robot_id, dof=dof, action=action,
            object_name=object_name, code=code,
        )

        annotate_resp = self.manager.generate(
            prompt=annotate_prompt,
            feature="codegen",
            system=_REVIEW_SYSTEM,
            temperature=0.1,
        )

        if annotate_resp.text is None:
            return CodeReviewResult(
                original_code=code,
                error=annotate_resp.error,
                model=annotate_resp.model,
                latency_s=annotate_resp.latency_s,
            )

        # Extract code from potential markdown fences
        annotated = _extract_code_block(annotate_resp.text) or annotate_resp.text

        # Step 2: Get structured issues
        issues_prompt = _ISSUES_TEMPLATE.format(
            language=language, language_tag=language_tag,
            robot_id=robot_id, action=action, code=code,
        )

        issues_resp = self.manager.generate(
            prompt=issues_prompt,
            feature="codegen",
            system=_ISSUES_SYSTEM,
            json_mode=True,
            temperature=0.1,
        )

        issues: list[str] = []
        suggestions: list[str] = []
        total_latency = annotate_resp.latency_s

        if issues_resp.text:
            total_latency += issues_resp.latency_s
            try:
                raw_json = issues_resp.text
                if not raw_json.lstrip().startswith("{"):
                    import re
                    match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                    raw_json = match.group(0) if match else raw_json
                parsed = loads_strict(raw_json)
                if isinstance(parsed, dict):
                    issues = [str(i) for i in parsed.get("issues", []) if isinstance(i, str)]
                    suggestions = [str(s) for s in parsed.get("suggestions", []) if isinstance(s, str)]
            except json.JSONDecodeError:
                pass

        return CodeReviewResult(
            original_code=code,
            annotated_code=annotated,
            issues=issues,
            suggestions=suggestions,
            model=annotate_resp.model,
            latency_s=total_latency,
            error=issues_resp.error if issues_resp.text is None else None,
        )


def _extract_code_block(text: str) -> str | None:
    """Extract code from markdown fences if present."""
    import re
    match = re.search(r'```[a-zA-Z]*\s*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
