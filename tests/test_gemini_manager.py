import json
import urllib.error

from roboweaver.nlu.gemini_manager import GeminiManager


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, _limit=-1):
        return json.dumps(self.body).encode()


def test_gemini_generate_uses_header_and_parses_usage(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({
            "candidates": [{"content": {"parts": [{"text": "result"}]}}],
            "usageMetadata": {"candidatesTokenCount": 4},
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    manager = GeminiManager(api_key="secret", default_model="gemini-3.5-flash-lite")
    response = manager.generate("hello", system="system", json_mode=True)

    assert response.text == "result"
    assert response.token_count == 4
    assert captured["request"].get_header("X-goog-api-key") == "secret"
    payload = json.loads(captured["request"].data)
    assert payload["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_reports_configuration_and_http_failure(monkeypatch):
    assert GeminiManager(api_key="").generate("hello").text is None

    def fail(_request, timeout):
        raise urllib.error.HTTPError("url", 429, "rate", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail)
    response = GeminiManager(api_key="secret").generate("hello")
    assert response.text is None
    assert "HTTP 429" in response.error
