"""End-to-end HTTP contract tests for the optional local-AI dashboard routes."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from roboweaver.dashboard.server import DashboardHTTPRequestHandler, ReusableHTTPServer
from roboweaver.nlu.ollama_manager import OllamaStreamChunk
from roboweaver.nlu.skill_explainer import SkillExplanation, SkillExplainer
from roboweaver.runtime.ai_recovery import AIRecoveryAdvice, AIRecoveryAdvisor


@pytest.fixture
def live_server():
    httpd = ReusableHTTPServer(("127.0.0.1", 0), DashboardHTTPRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _post(url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _get(request)


def test_compile_explain_is_additive_and_keeps_real_result(live_server):
    explanation = SkillExplanation(
        text="The real task graph picks and transfers the cube.",
        model="llama3.1:8b",
        latency_s=0.1,
    )
    with patch.object(SkillExplainer, "explain_compilation", return_value=explanation):
        status, _, raw = _get(
            f"{live_server}/api/compile?instruction=Pick+up+the+red+cube"
            "&robot=franka_panda&explain=1"
        )
    body = json.loads(raw)
    assert status == 200
    assert body["ir"]["skill"]["id"]
    assert body["explanation"] == explanation.text
    assert body["explanation_model"] == "llama3.1:8b"


def test_diagnose_accepts_a_diagnostic_code_and_preserves_rule_advice(live_server):
    advice = AIRecoveryAdvice(
        rule_based_action="REPLAN_APPROACH",
        rule_based_reason="Target is outside the reachable workspace.",
        ai_explanation=None,
        error="Ollama unreachable",
    )
    with patch.object(AIRecoveryAdvisor, "advise", return_value=advice):
        status, _, raw = _get(f"{live_server}/api/ai/diagnose?diagnostic=RW303")
    body = json.loads(raw)
    assert status == 200
    assert body["diagnostic_code"] == "RW303"
    assert body["failure_mode"] == "TARGET_UNREACHABLE"
    assert body["rule_based_action"] == "REPLAN_APPROACH"
    assert body["error"] == "Ollama unreachable"


def test_streaming_chat_proxies_tokens_as_ndjson(live_server):
    class FakeManager:
        def generate_stream(self, **_kwargs):
            yield OllamaStreamChunk(text="Hello ", model="local-model")
            yield OllamaStreamChunk(text="robot", model="local-model")
            yield OllamaStreamChunk(done=True, model="local-model", latency_s=0.2)

    with patch("roboweaver.nlu.ollama_manager.get_manager", return_value=FakeManager()):
        status, headers, raw = _get(f"{live_server}/api/ai/chat?stream=1&message=hello")
    chunks = [json.loads(line) for line in raw.splitlines()]
    assert status == 200
    assert headers["Content-Type"].startswith("application/x-ndjson")
    assert "".join(chunk["token"] for chunk in chunks) == "Hello robot"
    assert chunks[-1]["done"] is True


def test_model_config_refuses_a_model_that_is_not_pulled(live_server):
    class FakeManager:
        def list_models(self):
            return []

    with patch("roboweaver.nlu.ollama_manager.get_manager", return_value=FakeManager()):
        status, _, raw = _post(
            f"{live_server}/api/ai/config",
            {"feature": "chat", "model": "not-local:latest"},
        )
    assert status == 400
    assert "not pulled" in json.loads(raw)["error"]
