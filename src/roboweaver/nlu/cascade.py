"""Bounded provider cascade with exact cache and per-attempt provenance."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

from roboweaver.nlu.gemini_manager import GeminiManager
from roboweaver.nlu.ollama_manager import OllamaResponse, get_manager
from roboweaver.nlu.openrouter_manager import OpenRouterManager
from roboweaver.observability.cache import ExactResultCache, get_result_cache
from roboweaver.observability.traces import TraceRegistry, get_trace_registry


class GenerationManager(Protocol):
    provider: str

    def model_for_feature(self, feature: str) -> str: ...

    def generate(self, prompt: str, **kwargs: object) -> OllamaResponse: ...


@dataclass(frozen=True)
class CascadeCandidate:
    manager: GenerationManager
    model: str | None = None


@dataclass(frozen=True)
class CascadeResponse:
    text: str | None
    error: str | None
    provider: str
    model: str
    attempts: int
    parent_id: str
    cache_hit: bool = False
    token_count: int | None = None


def default_candidates(feature: str = "experiment") -> list[CascadeCandidate]:
    ollama = get_manager()
    gemini = GeminiManager()
    openrouter = OpenRouterManager()
    candidates: list[CascadeCandidate] = [CascadeCandidate(ollama, ollama.model_for_feature(feature))]
    if gemini.configured:
        candidates.append(CascadeCandidate(gemini, gemini.model_for_feature(feature)))
    if openrouter.configured:
        candidates.append(CascadeCandidate(openrouter, openrouter.model_for_feature(feature)))
    return candidates[:3]


class CascadeManager:
    """Try at most three explicit providers; every attempt is independently visible."""

    def __init__(
        self,
        candidates: list[CascadeCandidate] | None = None,
        *,
        cache: ExactResultCache | None = None,
        traces: TraceRegistry | None = None,
    ) -> None:
        chosen = candidates if candidates is not None else default_candidates()
        if not chosen or len(chosen) > 3:
            raise ValueError("A cascade requires 1-3 candidates.")
        self.candidates = list(chosen)
        self.cache = cache or get_result_cache()
        self.traces = traces or get_trace_registry()

    def _attempt_one(
        self, *, candidate: CascadeCandidate, attempt: int, requested_model: str,
        remaining: float, prompt: str, feature: str, system: str, json_mode: bool,
        temperature: float, per_attempt_timeout: float,
        validate: Callable[[str], None] | None, parent_id: str, cache_key: str,
    ) -> tuple[OllamaResponse | None, str | None]:
        """Try one candidate and record its trace. Returns `(response, None)` on
        success, or `(None, raw_error_text)` on a skip/failure -- the caller adds
        the provider prefix uniformly rather than repeating it per outcome."""
        if remaining <= 0:
            # A slow earlier attempt already consumed the shared time budget --
            # skip without a network call rather than risk this attempt alone
            # pushing the whole cascade past every client-side timeout above it.
            self.traces.record(
                parent_id=parent_id, feature=feature, provider=candidate.manager.provider,
                requested_model=requested_model, actual_model=requested_model, attempt=attempt,
                status="failed", latency_s=0.0, input_chars=len(prompt), output_chars=0,
                error_category="budget", error_message="skipped: cascade time budget exhausted",
                cache_key=cache_key,
            )
            return None, "skipped, cascade time budget exhausted"

        response = candidate.manager.generate(
            prompt, feature=feature, model=requested_model, system=system,
            json_mode=json_mode, temperature=temperature,
            timeout=max(1.0, min(float(per_attempt_timeout), 30.0, remaining)),
        )
        validation_error: str | None = None
        if response.text is not None and validate is not None:
            try:
                validate(response.text)
            except (TypeError, ValueError) as exc:
                validation_error = str(exc)[:300]
        succeeded = response.text is not None and validation_error is None
        error = validation_error or response.error
        self.traces.record(
            parent_id=parent_id, feature=feature, provider=candidate.manager.provider,
            requested_model=requested_model, actual_model=response.model or requested_model,
            attempt=attempt, status="succeeded" if succeeded else "failed",
            latency_s=response.latency_s, input_chars=len(prompt),
            output_chars=len(response.text or ""), token_count=response.token_count,
            error_category="validation" if validation_error else ("provider" if error else None),
            error_message=error, cache_key=cache_key,
        )
        return (response, None) if succeeded else (None, error or "no content")

    def generate(
        self,
        *,
        prompt: str,
        feature: str,
        system: str = "",
        json_mode: bool = False,
        temperature: float = 0.1,
        per_attempt_timeout: float = 20.0,
        max_total_seconds: float = 55.0,
        validate: Callable[[str], None] | None = None,
    ) -> CascadeResponse:
        if not prompt.strip():
            raise ValueError("Cascade prompt must not be empty.")
        parent_id = uuid.uuid4().hex
        candidate_signature = [
            [item.manager.provider, item.model or item.manager.model_for_feature(feature)]
            for item in self.candidates
        ]
        cache_key = self.cache.key_for({
            "v": 1,
            "feature": feature,
            "prompt": prompt,
            "system": system,
            "json_mode": json_mode,
            "temperature": round(float(temperature), 3),
            "candidates": candidate_signature,
        })
        cached = self.cache.get(cache_key)
        if cached is not None:
            try:
                if validate is not None:
                    validate(cached.text)
            except (TypeError, ValueError):
                self.cache.delete(cache_key)
            else:
                self.traces.record(
                    parent_id=parent_id,
                    feature=feature,
                    provider=cached.provider,
                    requested_model=cached.model,
                    actual_model=cached.model,
                    attempt=0,
                    status="cache_hit",
                    latency_s=0.0,
                    input_chars=len(prompt),
                    output_chars=len(cached.text),
                    token_count=cached.token_count,
                    cache_key=cache_key,
                )
                return CascadeResponse(
                    cached.text, None, cached.provider, cached.model, 0, parent_id, True, cached.token_count
                )

        errors: list[str] = []
        deadline = time.monotonic() + max(0.1, float(max_total_seconds))
        for attempt, candidate in enumerate(self.candidates, start=1):
            requested_model = candidate.model or candidate.manager.model_for_feature(feature)
            response, error = self._attempt_one(
                candidate=candidate, attempt=attempt, requested_model=requested_model,
                remaining=deadline - time.monotonic(), prompt=prompt, feature=feature,
                system=system, json_mode=json_mode, temperature=temperature,
                per_attempt_timeout=per_attempt_timeout, validate=validate,
                parent_id=parent_id, cache_key=cache_key,
            )
            if response is not None:
                assert response.text is not None
                self.cache.put(
                    cache_key,
                    text=response.text,
                    provider=candidate.manager.provider,
                    model=response.model or requested_model,
                    token_count=response.token_count,
                )
                return CascadeResponse(
                    response.text,
                    None,
                    candidate.manager.provider,
                    response.model or requested_model,
                    attempt,
                    parent_id,
                    False,
                    response.token_count,
                )
            errors.append(f"{candidate.manager.provider}: {error}")
        return CascadeResponse(None, "; ".join(errors), "none", "", len(self.candidates), parent_id)
