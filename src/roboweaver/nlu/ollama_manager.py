"""
Centralized Ollama Client & Model Manager — the single integration point for all
AI features across RoboWeaver.

Every module that calls an Ollama model (skill_explainer, ai_recovery,
skill_composer, ai_enrichment, ai_codegen, the existing ollama_parser and
connection_advisor) routes through this client instead of managing its own
urllib calls. Benefits:

  * One health-check, one probe, one list_models() — no N separate probes.
  * Per-feature model configuration via environment variables, with sensible
    defaults (all llama3.1:8b unless explicitly overridden).
  * Request-level latency tracking so the dashboard can report real performance.
  * Pull/model management endpoints for the frontend's model manager UI.
  * Honest failure reporting — every call that can't reach Ollama returns a
    stated error, never a silent fallback.

Uses only the standard library (urllib), matching RoboWeaver's zero-new-runtime-
dependency posture.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from roboweaver.json_utils import loads_strict


DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"

# Per-feature model environment variables. If not set, DEFAULT_MODEL is used.
# Users can override in .env: ROBOWEAVER_MODEL_EXPLAINER=codellama:13b
_FEATURE_MODEL_ENVS: dict[str, str] = {
    "parser": "ROBOWEAVER_MODEL_PARSER",
    "explainer": "ROBOWEAVER_MODEL_EXPLAINER",
    "recovery": "ROBOWEAVER_MODEL_RECOVERY",
    "composer": "ROBOWEAVER_MODEL_COMPOSER",
    "enrichment": "ROBOWEAVER_MODEL_ENRICHMENT",
    "codegen": "ROBOWEAVER_MODEL_CODEGEN",
    "advisor": "ROBOWEAVER_MODEL_ADVISOR",
    "chat": "ROBOWEAVER_MODEL_CHAT",
}

# Ordered by suitability, then by footprint.  Recommendations are advisory and
# only become active when a user explicitly selects a model.  The first pulled
# model in a feature's list is what the dashboard presents as "recommended".
_MODEL_RECOMMENDATIONS: dict[str, tuple[str, ...]] = {
    "parser": ("llama3.2:3b", "llama3.1:8b", "mistral:7b"),
    "explainer": ("llama3.1:8b", "mistral:7b", "llama3.2:3b"),
    "recovery": ("llama3.1:8b", "mistral:7b", "llama3.2:3b"),
    "composer": ("llama3.1:8b", "mistral:7b", "llama3.2:3b"),
    "enrichment": ("llama3.1:8b", "mistral:7b", "llama3.2:3b"),
    "codegen": ("codellama:7b", "qwen2.5-coder:7b", "llama3.1:8b"),
    "advisor": ("llama3.2:3b", "llama3.1:8b", "mistral:7b"),
    "chat": ("llama3.1:8b", "mistral:7b", "llama3.2:3b"),
}


def _config_value(key: str, default: str = "") -> str:
    """Read process environment first, then a small project-local `.env`.

    This intentionally implements only the simple ``KEY=value`` form used by
    `.env.example`; it does not execute shell syntax or mutate ``os.environ``.
    ``ROBOWEAVER_ENV_FILE`` can point at a different explicit file.
    """
    if key in os.environ:
        return os.environ[key]
    env_path = Path(os.environ.get("ROBOWEAVER_ENV_FILE", ".env"))
    try:
        if not env_path.is_file() or env_path.stat().st_size > 64 * 1024:
            return default
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            candidate, value = line.split("=", 1)
            if candidate.strip() == key:
                return value.strip().strip("\"'")
    except (OSError, UnicodeError):
        return default
    return default


def _http_error_text(exc: urllib.error.HTTPError, model: str) -> str:
    """Surface Ollama's safe JSON error without calling an HTTP error 'offline'."""
    detail = ""
    try:
        body = loads_strict(exc.read().decode("utf-8"))
        if isinstance(body.get("error"), str):
            detail = f": {body['error']}"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    return f"Ollama returned HTTP {exc.code} for model '{model}'{detail}"


def _validate_http_origin(value: str) -> str:
    """Accept an HTTP(S) origin only; urllib also supports unsafe local schemes."""
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("OLLAMA_HOST must be an HTTP(S) origin with a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("OLLAMA_HOST must not contain credentials.")
    if parsed.path or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("OLLAMA_HOST must not contain a path, parameters, query, or fragment.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("OLLAMA_HOST contains an invalid port.") from exc
    return candidate


@dataclass
class OllamaResponse:
    """Result of a single Ollama generate/chat call. `text` is None whenever
    the call failed — `error` always states why."""
    text: str | None
    error: str | None = None
    model: str = ""
    latency_s: float = 0.0
    token_count: int | None = None


@dataclass
class OllamaStreamChunk:
    """One chunk from Ollama's newline-delimited streaming response."""
    text: str = ""
    done: bool = False
    model: str = ""
    latency_s: float = 0.0
    token_count: int | None = None
    error: str | None = None


@dataclass
class OllamaModel:
    """A model currently pulled on the local Ollama instance."""
    name: str
    size_bytes: int = 0
    digest: str = ""
    modified_at: str = ""
    parameter_size: str = ""
    quantization: str = ""


@dataclass
class OllamaStatus:
    """Current state of the local Ollama server — all probed, nothing assumed."""
    available: bool
    host: str
    models: list[OllamaModel] = field(default_factory=list)
    default_model: str = DEFAULT_MODEL
    feature_models: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    error: str | None = None


class OllamaManager:
    """Centralized client for all Ollama interactions. Singleton-friendly but
    not enforced — tests construct separate instances with different hosts."""

    def __init__(self, host: str | None = None, default_model: str | None = None):
        self.host = _validate_http_origin(host or _config_value("OLLAMA_HOST", DEFAULT_HOST))
        self.default_model = default_model or _config_value("ROBOWEAVER_MODEL_DEFAULT", DEFAULT_MODEL)
        self._latency_history: list[float] = []
        self._runtime_feature_models: dict[str, str] = {}
        self._total_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0

    # ── Health & Discovery ────────────────────────────────────────────

    def is_available(self, timeout: float = 3.0) -> bool:
        """Real reachability probe. Returns False on any failure."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=timeout) as resp:  # nosec B310
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def get_version(self, timeout: float = 3.0) -> str | None:
        """Return the Ollama server version string, or None if unreachable."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/version", timeout=timeout) as resp:  # nosec B310
                body = loads_strict(resp.read().decode("utf-8"))
            return body.get("version")
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            return None

    def list_models(self, timeout: float = 5.0) -> list[OllamaModel]:
        """Models actually pulled on this Ollama instance — never a hardcoded list."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=timeout) as resp:  # nosec B310
                body = loads_strict(resp.read().decode("utf-8"))
            models = []
            for m in body.get("models", []):
                details = m.get("details", {})
                models.append(OllamaModel(
                    name=m.get("name", ""),
                    size_bytes=m.get("size", 0),
                    digest=m.get("digest", ""),
                    modified_at=m.get("modified_at", ""),
                    parameter_size=details.get("parameter_size", ""),
                    quantization=details.get("quantization_level", ""),
                ))
            return models
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            return []

    def model_for_feature(self, feature: str) -> str:
        """Resolve which model to use for a given feature. Checks the
        feature-specific env var first, then falls back to the default model."""
        if feature in self._runtime_feature_models:
            return self._runtime_feature_models[feature]
        env_key = _FEATURE_MODEL_ENVS.get(feature)
        if env_key:
            override = _config_value(env_key, "").strip()
            if override:
                return override
        return self.default_model

    def set_model_for_feature(self, feature: str, model: str) -> None:
        """Select a pulled model for this process without rewriting `.env`.

        Environment configuration remains the startup default.  Runtime choices
        are deliberately process-local and reversible, which keeps the dashboard
        from silently editing a user's configuration files.
        """
        if feature not in _FEATURE_MODEL_ENVS:
            raise ValueError(f"Unknown Ollama feature '{feature}'.")
        clean_model = model.strip()
        if not clean_model or len(clean_model) > 128 or any(c.isspace() for c in clean_model):
            raise ValueError("Model name must be 1-128 non-whitespace characters.")
        self._runtime_feature_models[feature] = clean_model

    def recommend_model(self, feature: str, available_models: list[str] | None = None) -> str:
        """Return a task-appropriate model, preferring one already pulled."""
        candidates = _MODEL_RECOMMENDATIONS.get(feature, (self.default_model,))
        if available_models is not None:
            pulled = set(available_models)
            for candidate in candidates:
                if candidate in pulled:
                    return candidate
            if self.model_for_feature(feature) in pulled:
                return self.model_for_feature(feature)
        return candidates[0]

    def status(self) -> OllamaStatus:
        """Full status probe — everything the dashboard AI panel needs."""
        available = self.is_available()
        models = self.list_models() if available else []
        version = self.get_version() if available else None

        feature_models = {
            feature: self.model_for_feature(feature)
            for feature in _FEATURE_MODEL_ENVS
        }

        return OllamaStatus(
            available=available,
            host=self.host,
            models=models,
            default_model=self.default_model,
            feature_models=feature_models,
            version=version,
            error=None if available else f"Ollama server unreachable at {self.host}",
        )

    # ── Model Management ──────────────────────────────────────────────

    def pull_model(self, model_name: str, timeout: float = 300.0) -> tuple[bool, str]:
        """Initiate a model pull. Returns (success, message).
        Note: This is a blocking call — for large models, the timeout should be generous."""
        payload = json.dumps({"name": model_name, "stream": False}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/pull",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                body = loads_strict(resp.read().decode("utf-8"))
            status = body.get("status", "")
            if "success" in status.lower():
                return True, f"Successfully pulled {model_name}"
            return True, status or f"Pull completed for {model_name}"
        except urllib.error.HTTPError as exc:
            return False, f"Ollama returned HTTP {exc.code} while pulling {model_name}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return False, f"Failed to pull {model_name}: {exc}"
        except json.JSONDecodeError:
            return False, f"Invalid response from Ollama while pulling {model_name}"

    # ── Generation ────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        feature: str = "chat",
        model: str | None = None,
        system: str | None = None,
        json_mode: bool = False,
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> OllamaResponse:
        """Send a generation request to the local Ollama server.

        Parameters:
            prompt: The user prompt.
            feature: Feature key for model resolution (e.g. 'explainer', 'recovery').
            model: Override model — if not provided, uses model_for_feature(feature).
            system: Optional system prompt.
            json_mode: If True, request JSON output format.
            timeout: HTTP timeout in seconds.
            temperature: Sampling temperature (lower = more deterministic).
        """
        resolved_model = model or self.model_for_feature(feature)

        body: dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            body["system"] = system
        if json_mode:
            body["format"] = "json"

        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                envelope = loads_strict(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=_http_error_text(exc, resolved_model),
                latency_s=time.monotonic() - start,
            )
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=f"Ollama unreachable at {self.host} (model={resolved_model}): {exc}",
                latency_s=time.monotonic() - start,
            )
        except json.JSONDecodeError as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=f"Ollama response was not valid JSON: {exc}",
                latency_s=time.monotonic() - start,
            )

        latency = time.monotonic() - start
        text = envelope.get("response", "")
        token_count = envelope.get("eval_count")
        if not isinstance(text, str) or not text:
            return OllamaResponse(
                text=None,
                model=resolved_model,
                error="Ollama returned an empty generation response.",
                latency_s=latency,
            )
        self._record_metrics(latency, prompt, text, token_count)

        return OllamaResponse(
            text=text,
            model=resolved_model,
            latency_s=latency,
            token_count=token_count,
        )

    def generate_stream(
        self,
        prompt: str,
        feature: str = "chat",
        model: str | None = None,
        system: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> Iterator[OllamaStreamChunk]:
        """Yield Ollama response tokens as they arrive from `/api/generate`."""
        resolved_model = model or self.model_for_feature(feature)
        body: dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if system:
            body["system"] = system
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.monotonic()
        pieces: list[str] = []
        token_count: int | None = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                for raw_line in resp:
                    if not raw_line.strip():
                        continue
                    try:
                        envelope = loads_strict(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        yield OllamaStreamChunk(
                            done=True, model=resolved_model,
                            latency_s=time.monotonic() - start,
                            error=f"Ollama stream contained invalid JSON: {exc}",
                        )
                        return
                    if envelope.get("error"):
                        yield OllamaStreamChunk(
                            done=True, model=resolved_model,
                            latency_s=time.monotonic() - start,
                            error=f"Ollama stream error: {envelope['error']}",
                        )
                        return
                    piece = envelope.get("response", "")
                    if isinstance(piece, str) and piece:
                        pieces.append(piece)
                        yield OllamaStreamChunk(text=piece, model=resolved_model)
                    if envelope.get("done"):
                        token_count = envelope.get("eval_count")
                        break
        except urllib.error.HTTPError as exc:
            yield OllamaStreamChunk(
                done=True, model=resolved_model,
                latency_s=time.monotonic() - start,
                error=_http_error_text(exc, resolved_model),
            )
            return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            yield OllamaStreamChunk(
                done=True, model=resolved_model,
                latency_s=time.monotonic() - start,
                error=f"Ollama unreachable at {self.host} (model={resolved_model}): {exc}",
            )
            return

        latency = time.monotonic() - start
        text = "".join(pieces)
        if text:
            self._record_metrics(latency, prompt, text, token_count)
        yield OllamaStreamChunk(
            done=True,
            model=resolved_model,
            latency_s=latency,
            token_count=token_count,
            error=None if text else "Ollama returned an empty streaming response.",
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        feature: str = "chat",
        model: str | None = None,
        json_mode: bool = False,
        timeout: float = 60.0,
        temperature: float = 0.1,
    ) -> OllamaResponse:
        """Send a chat-style (multi-turn) request to Ollama."""
        resolved_model = model or self.model_for_feature(feature)

        body: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            body["format"] = "json"

        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                envelope = loads_strict(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=_http_error_text(exc, resolved_model),
                latency_s=time.monotonic() - start,
            )
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=f"Ollama unreachable at {self.host}: {exc}",
                latency_s=time.monotonic() - start,
            )
        except json.JSONDecodeError as exc:
            return OllamaResponse(
                text=None, model=resolved_model,
                error=f"Ollama response was not valid JSON: {exc}",
                latency_s=time.monotonic() - start,
            )

        latency = time.monotonic() - start
        message = envelope.get("message", {})
        text = message.get("content", "")
        token_count = envelope.get("eval_count")
        if not isinstance(text, str) or not text:
            return OllamaResponse(
                text=None,
                model=resolved_model,
                error="Ollama returned an empty chat response.",
                latency_s=latency,
            )
        input_text = "\n".join(m.get("content", "") for m in messages)
        self._record_metrics(latency, input_text, text, token_count)

        return OllamaResponse(
            text=text,
            model=resolved_model,
            latency_s=latency,
            token_count=token_count,
        )

    # ── Metrics ───────────────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Cheap local estimate used only when Ollama omits exact counts."""
        return max(1, (len(text) + 3) // 4) if text else 0

    def _record_metrics(
        self, latency: float, input_text: str, output_text: str,
        output_tokens: int | None,
    ) -> None:
        self._latency_history.append(latency)
        self._total_calls += 1
        if len(self._latency_history) > 100:
            self._latency_history = self._latency_history[-100:]
        self._input_tokens += self.estimate_tokens(input_text)
        self._output_tokens += (
            output_tokens if isinstance(output_tokens, int)
            else self.estimate_tokens(output_text)
        )

    @property
    def avg_latency_s(self) -> float | None:
        """Average latency of recent calls, or None if no calls recorded."""
        if not self._latency_history:
            return None
        return sum(self._latency_history) / len(self._latency_history)

    @property
    def total_calls(self) -> int:
        return self._total_calls

    def to_status_dict(self) -> dict[str, Any]:
        """Dashboard-friendly JSON payload for /api/ai/status."""
        st = self.status()
        pulled_names = [m.name for m in st.models]
        return {
            "available": st.available,
            "host": st.host,
            "version": st.version,
            "default_model": st.default_model,
            "feature_models": st.feature_models,
            "recommendations": {
                feature: self.recommend_model(feature, pulled_names)
                for feature in _FEATURE_MODEL_ENVS
            },
            "models": [
                {
                    "name": m.name,
                    "size_bytes": m.size_bytes,
                    "parameter_size": m.parameter_size,
                    "quantization": m.quantization,
                }
                for m in st.models
            ],
            "avg_latency_s": round(self.avg_latency_s, 3) if self.avg_latency_s is not None else None,
            "total_calls": self.total_calls,
            "estimated_input_tokens": self._input_tokens,
            "estimated_output_tokens": self._output_tokens,
            "error": st.error,
        }


# Module-level singleton — constructed lazily, reconfigured by tests.
_default_manager: OllamaManager | None = None


def get_manager() -> OllamaManager:
    """Return the module-level OllamaManager, constructing it on first call."""
    global _default_manager
    if _default_manager is None:
        _default_manager = OllamaManager()
    return _default_manager
