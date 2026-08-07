import json

from roboweaver.nlu.cascade import CascadeCandidate, CascadeManager
from roboweaver.nlu.ollama_manager import OllamaResponse
from roboweaver.observability.cache import ExactResultCache
from roboweaver.observability.traces import TraceRegistry


class FakeManager:
    def __init__(self, provider, responses):
        self.provider = provider
        self.responses = list(responses)
        self.calls = 0

    def model_for_feature(self, feature):
        return f"{self.provider}-{feature}"

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def test_cascade_falls_back_traces_attempts_and_caches_valid_result():
    first = FakeManager("ollama", [OllamaResponse(None, "offline", "local", 0.01)])
    second = FakeManager("gemini", [OllamaResponse('{"ok":true}', None, "flash-lite", 0.02, 7)])
    cache = ExactResultCache(max_entries=10, ttl_seconds=60)
    traces = TraceRegistry(max_entries=10)
    cascade = CascadeManager(
        [CascadeCandidate(first), CascadeCandidate(second)], cache=cache, traces=traces
    )

    def validate(value):
        if json.loads(value) != {"ok": True}:
            raise ValueError("invalid")

    result = cascade.generate(prompt="design", feature="experiment", json_mode=True, validate=validate)
    cached = cascade.generate(prompt="design", feature="experiment", json_mode=True, validate=validate)

    assert result.provider == "gemini"
    assert result.attempts == 2
    assert cached.cache_hit is True
    assert first.calls == 1
    assert second.calls == 1
    report = traces.report()
    assert report["totals"]["failed"] == 1
    assert report["totals"]["succeeded"] == 1
    assert report["totals"]["cache_hits"] == 1
    assert all("design" not in json.dumps(item) for item in report["recent"])


def test_cascade_rejects_more_than_three_candidates():
    manager = FakeManager("fake", [])
    try:
        CascadeManager([CascadeCandidate(manager)] * 4)
    except ValueError as exc:
        assert "1-3" in str(exc)
    else:
        raise AssertionError("expected a bounded-cascade error")
