import json
import time

from roboweaver.nlu.cascade import CascadeCandidate, CascadeManager
from roboweaver.nlu.ollama_manager import OllamaResponse
from roboweaver.observability.cache import ExactResultCache
from roboweaver.observability.traces import TraceRegistry


class FakeManager:
    def __init__(self, provider, responses, delay_s=0.0):
        self.provider = provider
        self.responses = list(responses)
        self.calls = 0
        self.delay_s = delay_s

    def model_for_feature(self, feature):
        return f"{self.provider}-{feature}"

    def generate(self, prompt, **kwargs):
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        return self.responses.pop(0)


def test_cascade_falls_back_traces_attempts_and_caches_valid_result():
    first = FakeManager("ollama", [OllamaResponse(None, "offline", "local", 0.01)])
    second = FakeManager("openrouter", [OllamaResponse('{"ok":true}', None, "flash-lite", 0.02, 7)])
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

    assert result.provider == "openrouter"
    assert result.attempts == 2
    assert cached.cache_hit is True
    assert first.calls == 1
    assert second.calls == 1
    report = traces.report()
    assert report["totals"]["failed"] == 1
    assert report["totals"]["succeeded"] == 1
    assert report["totals"]["cache_hits"] == 1
    assert all("design" not in json.dumps(item) for item in report["recent"])


def test_cascade_skips_later_candidates_once_the_time_budget_is_spent():
    # A slow first provider must not be allowed to push the whole cascade past
    # every client-side HTTP timeout above it -- this is the exact bug a real
    # user hit against /api/research/plan (backend cascade exceeded the
    # frontend's fetch timeout because per-attempt timeouts alone don't bound
    # the sum across multiple sequential attempts).
    slow = FakeManager("ollama", [OllamaResponse(None, "slow failure", "local", 0.2)], delay_s=0.2)
    unreachable_budget = FakeManager("openrouter", [OllamaResponse('{"ok":true}', None, "flash-lite", 0.0, 1)])
    cache = ExactResultCache(max_entries=10, ttl_seconds=60)
    traces = TraceRegistry(max_entries=10)
    cascade = CascadeManager(
        [CascadeCandidate(slow), CascadeCandidate(unreachable_budget)], cache=cache, traces=traces
    )

    started = time.monotonic()
    result = cascade.generate(prompt="design", feature="experiment", max_total_seconds=0.05)
    elapsed = time.monotonic() - started

    assert result.text is None
    assert slow.calls == 1
    assert unreachable_budget.calls == 0  # skipped without a network call
    assert elapsed < 1.0  # did not also wait out the second candidate's own timeout
    assert "budget exhausted" in result.error


def test_cascade_rejects_more_than_three_candidates():
    manager = FakeManager("fake", [])
    try:
        CascadeManager([CascadeCandidate(manager)] * 4)
    except ValueError as exc:
        assert "1-3" in str(exc)
    else:
        raise AssertionError("expected a bounded-cascade error")
