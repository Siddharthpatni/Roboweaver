"""Small exact-result cache for model responses; never stores API credentials."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheValue:
    text: str
    provider: str
    model: str
    token_count: int | None
    expires_at: float


class ExactResultCache:
    def __init__(self, max_entries: int = 256, ttl_seconds: float = 3600.0) -> None:
        if not 1 <= max_entries <= 10_000:
            raise ValueError("max_entries must be between 1 and 10000.")
        if not 1 <= ttl_seconds <= 7 * 24 * 3600:
            raise ValueError("ttl_seconds must be between 1 second and 7 days.")
        self.max_entries = max_entries
        self.ttl_seconds = float(ttl_seconds)
        self._items: OrderedDict[str, CacheValue] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @staticmethod
    def key_for(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, key: str) -> CacheValue | None:
        now = time.monotonic()
        with self._lock:
            value = self._items.get(key)
            if value is None:
                self._misses += 1
                return None
            if value.expires_at <= now:
                self._items.pop(key, None)
                self._misses += 1
                return None
            self._items.move_to_end(key)
            self._hits += 1
            return value

    def put(self, key: str, *, text: str, provider: str, model: str, token_count: int | None) -> None:
        value = CacheValue(text, provider, model, token_count, time.monotonic() + self.ttl_seconds)
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
                self._evictions += 1

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "entries": len(self._items),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
            }


_RESULT_CACHE = ExactResultCache()


def get_result_cache() -> ExactResultCache:
    return _RESULT_CACHE
