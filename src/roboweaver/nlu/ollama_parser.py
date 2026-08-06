"""
Ollama-backed Semantic Parser -- an optional, local, fully offline alternative to
the deterministic keyword parser in compiler.py's SkillCompiler._parse_intent().

This is additive, never a silent replacement: RoboWeaver's default Task Understanding
stage stays the deterministic regex/keyword parser (docs/REDESIGN.md's "Determinism
before intelligence" principle) because it's reproducible -- the same instruction
always compiles to the same RoboIR, with no network dependency and no model-version
drift. This module exists for when a user explicitly wants an LLM in that stage,
running fully offline against a locally-hosted Ollama server (never a cloud API), and
it fails honestly -- returns a result with intent=None and a stated reason -- rather
than silently guessing when Ollama isn't reachable or its output can't be mapped onto
RoboWeaver's real Action taxonomy.

Uses only the standard library (urllib), matching the zero-new-runtime-dependency
posture already used for optional integrations elsewhere in RoboWeaver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from roboweaver.nlu.ollama_manager import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    OllamaManager,
    get_manager,
)
from roboweaver.types import Action, SkillIntent

_VALID_ACTIONS = {a.value for a in Action}

_PROMPT_TEMPLATE = """You translate a single robot-task instruction into strict JSON.
Output ONLY JSON, no prose, no markdown fences, matching exactly this shape:
{{"action": "<one of: """ + ", ".join(sorted(_VALID_ACTIONS)) + """>", "object_name": "<short_snake_case_object_id>", "parameters": {{}}}}
Pick the single closest action from that exact list. If nothing fits well, use "PICK".

Instruction: "{instruction}"
JSON:"""


@dataclass
class OllamaParseResult:
    """intent is None whenever the parse could not be trusted -- unreachable
    server, malformed JSON, or an action outside RoboWeaver's real taxonomy.
    error explains which, so a caller can log the real reason instead of
    silently falling back."""

    intent: SkillIntent | None
    raw_response: str
    model: str
    error: str | None = None
    parameters_dropped: list[str] = field(default_factory=list)


class OllamaIntentParser:
    """Calls a local Ollama server's /api/generate endpoint. Never contacts any
    host other than the one explicitly configured (default: localhost) -- this
    is an offline-model integration, not a cloud LLM client."""

    def __init__(
        self, model: str | None = None, host: str | None = None,
        timeout: float = 30.0, manager: OllamaManager | None = None,
    ):
        self.timeout = timeout
        self.manager = manager or (
            OllamaManager(host=host, default_model=model) if host is not None else get_manager()
        )
        self.model = model or self.manager.model_for_feature("parser")
        self.host = self.manager.host

    def is_available(self) -> bool:
        """Real reachability probe -- a genuine HTTP request to the local Ollama
        server, honestly reporting False on any failure rather than assuming
        availability. Mirrors the honest-hardware-bridge pattern used throughout
        RoboWeaver's real hardware drivers."""
        return self.manager.is_available(timeout=3.0)

    def list_models(self) -> list[str]:
        """Real models actually pulled on this Ollama instance -- never a
        hardcoded/assumed list."""
        return [m.name for m in self.manager.list_models(timeout=3.0)]

    def parse(self, instruction: str) -> OllamaParseResult:
        prompt = _PROMPT_TEMPLATE.format(instruction=instruction)
        response = self.manager.generate(
            prompt,
            feature="parser",
            model=self.model,
            json_mode=True,
            timeout=self.timeout,
            temperature=0.0,
        )
        if response.text is None:
            return OllamaParseResult(
                intent=None, raw_response="", model=self.model,
                error=response.error,
            )
        return self._parse_model_output(response.text)

    def _parse_model_output(self, raw_text: str) -> OllamaParseResult:
        try:
            parsed: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return OllamaParseResult(
                intent=None, raw_response=raw_text, model=self.model,
                error=f"Model output was not valid JSON: {exc}",
            )

        action_str = str(parsed.get("action", "")).strip().upper()
        if action_str not in _VALID_ACTIONS:
            return OllamaParseResult(
                intent=None, raw_response=raw_text, model=self.model,
                error=f"Model returned action '{action_str}', which is not in RoboWeaver's Action taxonomy ({sorted(_VALID_ACTIONS)}).",
            )

        object_name = str(parsed.get("object_name") or "object").strip() or "object"
        raw_params = parsed.get("parameters")
        parameters: dict[str, float] = {}
        dropped: list[str] = []
        if isinstance(raw_params, dict):
            for key, value in raw_params.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    parameters[key] = float(value)
                else:
                    dropped.append(key)

        intent = SkillIntent(action=Action(action_str), object_name=object_name, parameters=parameters)
        return OllamaParseResult(intent=intent, raw_response=raw_text, model=self.model, parameters_dropped=dropped)
