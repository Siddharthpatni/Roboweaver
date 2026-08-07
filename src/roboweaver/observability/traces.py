"""Bounded, prompt-free traces inspired by Sentinel's attempt provenance model.

Only request digests and lengths are retained. Prompts, responses and credentials
are deliberately excluded so the dashboard can diagnose providers without becoming
a second sensitive-data store.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import Counter, deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CallTrace:
    trace_id: str
    parent_id: str
    timestamp: float
    feature: str
    provider: str
    requested_model: str
    actual_model: str
    attempt: int
    status: str
    latency_s: float
    input_chars: int
    output_chars: int
    token_count: int | None = None
    error_category: str | None = None
    error_message: str | None = None
    cache_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = round(self.timestamp, 3)
        data["latency_s"] = round(self.latency_s, 4)
        return data


class TraceRegistry:
    """Thread-safe in-memory trace ring with aggregate health metrics."""

    def __init__(self, max_entries: int = 500) -> None:
        if not 10 <= max_entries <= 10_000:
            raise ValueError("max_entries must be between 10 and 10000.")
        self._items: deque[CallTrace] = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def record(
        self,
        *,
        parent_id: str,
        feature: str,
        provider: str,
        requested_model: str,
        actual_model: str,
        attempt: int,
        status: str,
        latency_s: float,
        input_chars: int,
        output_chars: int,
        token_count: int | None = None,
        error_category: str | None = None,
        error_message: str | None = None,
        cache_key: str | None = None,
    ) -> CallTrace:
        if status not in {"succeeded", "failed", "cache_hit", "blocked"}:
            raise ValueError(f"Unknown trace status '{status}'.")
        trace = CallTrace(
            trace_id=uuid.uuid4().hex,
            parent_id=parent_id,
            timestamp=time.time(),
            feature=feature[:64],
            provider=provider[:32],
            requested_model=requested_model[:160],
            actual_model=actual_model[:160],
            attempt=max(0, int(attempt)),
            status=status,
            latency_s=max(0.0, float(latency_s)),
            input_chars=max(0, int(input_chars)),
            output_chars=max(0, int(output_chars)),
            token_count=token_count if isinstance(token_count, int) and token_count >= 0 else None,
            error_category=error_category[:64] if error_category else None,
            error_message=error_message[:300] if error_message else None,
            cache_key=cache_key[:16] if cache_key else None,
        )
        with self._lock:
            self._items.append(trace)
        return trace

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def snapshot(self) -> list[CallTrace]:
        with self._lock:
            return list(self._items)

    def report(self, limit: int = 50) -> dict[str, Any]:
        items = self.snapshot()
        bounded_limit = max(1, min(int(limit), 200))
        statuses = Counter(item.status for item in items)
        providers = Counter(item.provider for item in items)
        completed = statuses["succeeded"] + statuses["failed"]
        latencies = sorted(item.latency_s for item in items if item.status in {"succeeded", "failed"})
        p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
        return {
            "privacy": "Prompts, responses, API keys, and target addresses are not stored.",
            "totals": {
                "traces": len(items),
                "requests": len({item.parent_id for item in items}),
                "succeeded": statuses["succeeded"],
                "failed": statuses["failed"],
                "blocked": statuses["blocked"],
                "cache_hits": statuses["cache_hit"],
                "tokens": sum(item.token_count or 0 for item in items),
            },
            "success_rate": round(statuses["succeeded"] / completed, 4) if completed else None,
            "cache_hit_rate": round(statuses["cache_hit"] / len(items), 4) if items else 0.0,
            "p95_latency_s": round(latencies[p95_index], 4) if latencies else None,
            "providers": dict(sorted(providers.items())),
            "recent": [item.to_dict() for item in reversed(items[-bounded_limit:])],
        }


_TRACE_REGISTRY = TraceRegistry()


def get_trace_registry() -> TraceRegistry:
    return _TRACE_REGISTRY
