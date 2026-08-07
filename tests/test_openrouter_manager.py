from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

from roboweaver.nlu.openrouter_manager import OpenRouterManager


class FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self, size: int = -1):
        return self._body if size < 0 else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


@patch("roboweaver.nlu.openrouter_manager.urllib.request.urlopen")
def test_openrouter_generate_uses_server_side_bearer_key(mock_urlopen):
    mock_urlopen.return_value = FakeHTTPResponse(json.dumps({
        "model": "example/coder:free",
        "choices": [{"message": {"content": "reviewed code"}}],
        "usage": {"completion_tokens": 12},
    }).encode())
    manager = OpenRouterManager(api_key="sk-or-v1-test-key-with-safe-length", default_model="openrouter/free")

    result = manager.generate(
        "Review this", system="Be careful", json_mode=True, model="openrouter/free"
    )

    assert result.text == "reviewed code"
    assert result.model == "example/coder:free"
    assert result.token_count == 12
    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-or-v1-test-key-with-safe-length"
    payload = json.loads(request.data)
    assert payload["model"] == "openrouter/free"
    assert payload["response_format"] == {"type": "json_object"}


@patch("roboweaver.nlu.openrouter_manager.urllib.request.urlopen")
def test_named_free_codegen_model_has_free_router_fallback(mock_urlopen):
    mock_urlopen.return_value = FakeHTTPResponse(json.dumps({
        "model": "cohere/north-mini-code:free",
        "choices": [{"message": {"content": "reviewed code"}}],
    }).encode())
    manager = OpenRouterManager(
        api_key="sk-or-v1-test-key-with-safe-length",
        default_model="cohere/north-mini-code:free",
    )

    result = manager.generate(
        "Review this", feature="codegen", model="cohere/north-mini-code:free"
    )

    assert result.model == "cohere/north-mini-code:free"
    payload = json.loads(mock_urlopen.call_args.args[0].data)
    assert "model" not in payload
    assert payload["models"] == ["cohere/north-mini-code:free", "openrouter/free"]


@patch("roboweaver.nlu.openrouter_manager.urllib.request.urlopen")
def test_openrouter_missing_key_fails_without_network_call(mock_urlopen):
    result = OpenRouterManager(api_key="").generate("Review this")
    assert result.text is None
    assert "OPENROUTER_API_KEY" in (result.error or "")
    mock_urlopen.assert_not_called()


@patch("roboweaver.nlu.openrouter_manager.urllib.request.urlopen")
def test_openrouter_http_error_is_bounded_and_does_not_expose_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://openrouter.ai/api/v1/chat/completions",
        429,
        "rate limited",
        {},
        io.BytesIO(b'{"error":{"message":"Free-model limit reached"}}'),
    )
    secret = "sk-or-v1-never-include-this-key-in-errors"
    result = OpenRouterManager(api_key=secret).generate("Review this")
    assert result.text is None
    assert "HTTP 429" in (result.error or "")
    assert "Free-model limit reached" in (result.error or "")
    assert secret not in (result.error or "")
