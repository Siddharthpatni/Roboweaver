"""Small, explicit OpenRouter client for optional cloud-assisted features.

RoboWeaver remains deterministic without this module.  The client is enabled only
when an operator selects ``openrouter`` and supplies ``OPENROUTER_API_KEY``.  It uses
the standard library, never logs the key, and defaults to OpenRouter's free-model
router instead of pinning a free model whose availability may change.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from roboweaver.json_utils import loads_strict
from roboweaver.nlu.ollama_manager import OllamaResponse, _config_value


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "openrouter/free"
_MAX_KEY_LENGTH = 512
_MAX_MODEL_LENGTH = 160
_MAX_OUTPUT_TOKENS = 4096
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _safe_model_name(value: str) -> str:
    model = value.strip()
    if not model or len(model) > _MAX_MODEL_LENGTH:
        raise ValueError(f"OpenRouter model must be 1-{_MAX_MODEL_LENGTH} characters.")
    if any(char.isspace() or ord(char) < 0x20 for char in model):
        raise ValueError("OpenRouter model must not contain whitespace or control characters.")
    return model


def _configured_key() -> str:
    key = _config_value("OPENROUTER_API_KEY", "").strip()
    if not key:
        return ""
    if len(key) > _MAX_KEY_LENGTH or any(char.isspace() or ord(char) < 0x20 for char in key):
        return ""
    return key


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = loads_strict(exc.read(65_537).decode("utf-8"))
        error = body.get("error", {})
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:300]
        if isinstance(error, str):
            return error[:300]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    return "request rejected"


class OpenRouterManager:
    """OpenAI-compatible chat-completions client with RoboWeaver's response shape."""

    provider = "openrouter"

    def __init__(self, api_key: str | None = None, default_model: str | None = None):
        self._api_key = (api_key if api_key is not None else _configured_key()).strip()
        if self._api_key and (
            len(self._api_key) > _MAX_KEY_LENGTH
            or any(char.isspace() or ord(char) < 0x20 for char in self._api_key)
        ):
            raise ValueError("OPENROUTER_API_KEY contains invalid characters or is too long.")
        self.default_model = _safe_model_name(
            default_model or _config_value("ROBOWEAVER_OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL)
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def model_for_feature(self, feature: str) -> str:
        feature_key = f"ROBOWEAVER_OPENROUTER_MODEL_{feature.upper()}"
        return _safe_model_name(_config_value(feature_key, self.default_model))

    def generate(
        self,
        prompt: str,
        feature: str = "codegen",
        system: str = "",
        model: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.1,
        timeout: float = 60.0,
        max_tokens: int = 2048,
    ) -> OllamaResponse:
        selected_model = _safe_model_name(model or self.model_for_feature(feature))
        if not self.configured:
            return OllamaResponse(
                text=None,
                error="OpenRouter is not configured. Set OPENROUTER_API_KEY in the ignored local .env file.",
                model=selected_model,
            )
        if not isinstance(prompt, str) or not prompt.strip():
            return OllamaResponse(text=None, error="OpenRouter prompt must not be empty.", model=selected_model)
        bounded_tokens = max(1, min(int(max_tokens), _MAX_OUTPUT_TOKENS))
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": max(0.0, min(float(temperature), 1.0)),
            "max_tokens": bounded_tokens,
            "stream": False,
        }
        # A named free coding model gives reviews a code-capable primary while
        # OpenRouter's free router keeps the optional annotation resilient when
        # that changing free endpoint is unavailable. Paid/explicit models are
        # never silently replaced with another model.
        if selected_model.endswith(":free") and selected_model != OPENROUTER_DEFAULT_MODEL:
            payload.pop("model")
            payload["models"] = [selected_model, OPENROUTER_DEFAULT_MODEL]
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(  # nosec B310 - fixed HTTPS origin
            OPENROUTER_CHAT_URL,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "X-Title": "RoboWeaver",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                return OllamaResponse(
                    text=None,
                    error="OpenRouter response exceeded the 2 MiB safety limit.",
                    model=selected_model,
                    latency_s=time.perf_counter() - started,
                )
            body = loads_strict(raw.decode("utf-8"))
            choices = body.get("choices", [])
            content = choices[0].get("message", {}).get("content") if choices else None
            if not isinstance(content, str) or not content.strip():
                return OllamaResponse(
                    text=None,
                    error="OpenRouter returned no text content.",
                    model=str(body.get("model") or selected_model),
                    latency_s=time.perf_counter() - started,
                )
            usage = body.get("usage", {})
            completion_tokens = usage.get("completion_tokens")
            return OllamaResponse(
                text=content,
                model=str(body.get("model") or selected_model),
                latency_s=time.perf_counter() - started,
                token_count=completion_tokens if isinstance(completion_tokens, int) else None,
            )
        except urllib.error.HTTPError as exc:
            return OllamaResponse(
                text=None,
                error=f"OpenRouter returned HTTP {exc.code}: {_error_detail(exc)}",
                model=selected_model,
                latency_s=time.perf_counter() - started,
            )
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            return OllamaResponse(
                text=None,
                error=f"OpenRouter request failed: {type(exc).__name__}",
                model=selected_model,
                latency_s=time.perf_counter() - started,
            )


def openrouter_status() -> dict[str, Any]:
    manager = OpenRouterManager()
    return {
        "configured": manager.configured,
        "model": manager.default_model,
        "codegen_model": manager.model_for_feature("codegen"),
        "provider": manager.provider,
        "remote": True,
    }
