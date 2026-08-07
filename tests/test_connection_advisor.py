"""
Tests for the LLM connection advisor (src/roboweaver/nlu/connection_advisor.py).

No network calls: every test drives a fake backend, so the suite stays offline,
free, and deterministic. What is under test is the *validation* layer -- the
part that decides whether a model's answer is safe to hand to the driver -- plus
the response-shape handling that real providers turned out to need.
"""

from __future__ import annotations

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.nlu.connection_advisor import (
    SUPPORTED_PROTOCOLS,
    ConnectionAdvisor,
    _Backend,
    _coerce_json_text,
    advisor_status,
    build_advisor,
)

ENDPOINT = {
    "host": "192.168.1.40",
    "port": 30002,
    "banner": "",
    "hostname": "ur-controller.local",
    "robot_type_guess": "Universal Robots (UR)",
    "latency_ms": 2.0,
}


class FakeBackend(_Backend):
    name = "fake"
    model = "fake-model"

    def __init__(self, payload: str = "", error: str | None = None):
        self.payload = payload
        self.error = error

    def complete(self, prompt: str) -> tuple[str, str | None]:
        return self.payload, self.error


def _advise(payload: str = "", error: str | None = None):
    return ConnectionAdvisor(FakeBackend(payload, error)).advise(ENDPOINT)


def test_valid_advice_is_accepted_and_uri_built():
    real_id = "ur5e"
    assert real_id in ROBOT_REGISTRY
    advice = _advise(
        f'{{"robot_id":"{real_id}","protocol":"sim","confidence":0.9,"reasoning":"port 30002"}}'
    )
    assert advice.error is None
    assert advice.robot_id == real_id
    assert advice.protocol == "sim"
    # The URI is derived from the observed endpoint, never from the model.
    assert advice.uri == "sim://192.168.1.40:30002"
    assert advice.confidence == 0.9


def test_hallucinated_robot_id_is_rejected():
    """The registry is the authority -- an invented id must never reach the driver."""
    advice = _advise('{"robot_id":"skynet_t800","protocol":"sim","confidence":0.99,"reasoning":"x"}')
    assert advice.robot_id is None
    assert advice.error is not None
    assert "ROBOT_REGISTRY" in advice.error


def test_unsupported_protocol_is_rejected():
    """Only protocols with a real bridge implementation are allowed through."""
    advice = _advise('{"robot_id":"ur5e","protocol":"telnet","confidence":0.9,"reasoning":"x"}')
    assert advice.protocol is None
    assert advice.error is not None
    for proto in SUPPORTED_PROTOCOLS:
        assert proto in advice.error


def test_non_json_output_fails_honestly():
    advice = _advise("I reckon it's a UR5e, mate.")
    assert advice.robot_id is None
    assert advice.error is not None


def test_backend_error_is_surfaced_not_swallowed():
    advice = _advise(error="Ollama unreachable at http://localhost:11434")
    assert advice.robot_id is None
    assert advice.error is not None
    assert "unreachable" in advice.error


def test_empty_response_does_not_crash():
    """A provider returning nothing must produce a stated error, not a traceback."""
    advice = _advise("")
    assert advice.robot_id is None
    assert advice.error is not None


def test_confidence_is_clamped():
    advice = _advise('{"robot_id":"ur5e","protocol":"sim","confidence":9.5,"reasoning":"x"}')
    assert advice.confidence == 1.0


def test_non_finite_confidence_is_rejected():
    advice = _advise('{"robot_id":"ur5e","protocol":"sim","confidence":NaN,"reasoning":"x"}')
    assert advice.robot_id is None
    assert advice.error is not None


def test_markdown_fenced_json_is_recovered():
    """Local models may fence replies; valid fenced JSON remains usable."""
    fenced = '```json\n{"robot_id": "ur5e", "protocol": "sim", "confidence": 0.92, "reasoning": "port 30002"}\n```'
    advice = _advise(fenced)
    assert advice.error is None
    assert advice.robot_id == "ur5e"
    assert advice.confidence == 0.92


def test_coerce_json_text_handles_prose_and_fences():
    assert _coerce_json_text('{"a":1}') == '{"a":1}'
    assert _coerce_json_text('```json\n{"a":1}\n```') == '{"a":1}'
    assert _coerce_json_text('Sure! {"a":1} hope that helps') == '{"a":1}'


def test_advisor_status_reports_local_and_explicit_remote_options():
    status = advisor_status()
    assert status["providers"] == ["ollama", "openrouter"]
    assert status["ollama_host"].startswith(("http://", "https://"))
    assert isinstance(status["openrouter_configured"], bool)
    assert isinstance(status["openrouter_codegen_model"], str)
    assert "remote" in status["remote_privacy_notice"].lower()


def test_advisor_factory_supports_explicit_openrouter_and_rejects_unknown_provider():
    import pytest

    assert build_advisor("openrouter").backend.name == "openrouter"
    with pytest.raises(ValueError, match="ollama.*openrouter"):
        build_advisor("remote")
