"""Optional Gemini API client with the same response contract as Ollama.

The API key remains server-side. The default model is the current low-cost stable
Flash-Lite family and can be overridden without changing compiler code.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from roboweaver.json_utils import loads_strict
from roboweaver.nlu.ollama_manager import OllamaResponse, _config_value


GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_KEY_LENGTH = 512
_MAX_MODEL_LENGTH = 128
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _safe_model(value: str) -> str:
    model = value.strip()
    if not model or len(model) > _MAX_MODEL_LENGTH:
        raise ValueError(f"Gemini model must be 1-{_MAX_MODEL_LENGTH} characters.")
    if any(not (char.isalnum() or char in "-._") for char in model):
        raise ValueError("Gemini model contains unsupported characters.")
    return model


def _configured_key() -> str:
    key = _config_value("GEMINI_API_KEY", "").strip()
    if not key or len(key) > _MAX_KEY_LENGTH or any(char.isspace() for char in key):
        return ""
    return key


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = loads_strict(exc.read(65_537).decode("utf-8"))
        message = body.get("error", {}).get("message")
        if isinstance(message, str):
            return message[:300]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        pass
    return "request rejected"


class GeminiManager:
    provider = "gemini"

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        self._api_key = (api_key if api_key is not None else _configured_key()).strip()
        if self._api_key and (len(self._api_key) > _MAX_KEY_LENGTH or any(c.isspace() for c in self._api_key)):
            raise ValueError("GEMINI_API_KEY contains whitespace or is too long.")
        self.default_model = _safe_model(
            default_model or _config_value("ROBOWEAVER_GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def model_for_feature(self, feature: str) -> str:
        key = f"ROBOWEAVER_GEMINI_MODEL_{feature.upper()}"
        return _safe_model(_config_value(key, self.default_model))

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
        selected = _safe_model(model or self.model_for_feature(feature))
        if not self.configured:
            return OllamaResponse(
                None,
                "Gemini is not configured. Set GEMINI_API_KEY in the ignored local .env file.",
                selected,
            )
        if not isinstance(prompt, str) or not prompt.strip():
            return OllamaResponse(None, "Gemini prompt must not be empty.", selected)
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": max(0.0, min(float(temperature), 1.0)),
                "maxOutputTokens": max(1, min(int(max_tokens), 4096)),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        request = urllib.request.Request(  # nosec B310 - fixed HTTPS API root
            f"{GEMINI_API_ROOT}/{selected}:generateContent",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            latency = time.perf_counter() - started
            if len(raw) > _MAX_RESPONSE_BYTES:
                return OllamaResponse(None, "Gemini response exceeded 2 MiB.", selected, latency)
            body = loads_strict(raw.decode("utf-8"))
            candidates = body.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
            if not text.strip():
                return OllamaResponse(None, "Gemini returned no text content.", selected, latency)
            usage = body.get("usageMetadata", {})
            tokens = usage.get("candidatesTokenCount")
            return OllamaResponse(text, None, selected, latency, tokens if isinstance(tokens, int) else None)
        except urllib.error.HTTPError as exc:
            return OllamaResponse(
                None,
                f"Gemini returned HTTP {exc.code}: {_error_detail(exc)}",
                selected,
                time.perf_counter() - started,
            )
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            return OllamaResponse(
                None,
                f"Gemini request failed: {type(exc).__name__}",
                selected,
                time.perf_counter() - started,
            )


def gemini_status() -> dict[str, Any]:
    manager = GeminiManager()
    return {
        "configured": manager.configured,
        "model": manager.default_model,
        "experiment_model": manager.model_for_feature("experiment"),
        "provider": manager.provider,
        "remote": True,
    }
