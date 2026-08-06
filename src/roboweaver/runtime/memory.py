"""
Episodic execution memory (docs/COMPILER_ROADMAP.md v2 vision, item 6). Real,
persisted (JSONL, one file per robot) history of executed skills -- task, plan,
execution outcome, per run -- following registry/repository.py's existing
local-JSON-file convention (not SQLite, matching REDESIGN.md §10's stated MVP scope).

Zero accumulated history exists in this repo today; this is the mechanism items 7
(case-based recovery) and 12 (self-learning compiler suggestions) consume once real
usage produces real data -- not a claim that either has learned anything yet.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from roboweaver.identifiers import require_safe_identifier
from roboweaver.json_utils import loads_strict


logger = logging.getLogger(__name__)
MAX_RECORD_BYTES = 1_048_576
MAX_QUERY_LIMIT = 10_000


class ExecutionMemoryStore:
    """Opt-in: nothing writes here unless a caller explicitly attaches a store
    (e.g. SkillRuntime(memory_store=ExecutionMemoryStore(...))) -- so the existing
    test suite's many direct SkillRuntime.execute() calls never touch disk."""

    def __init__(self, store_dir: str | Path | None = None):
        self.store_dir = Path(store_dir) if store_dir is not None else Path.cwd() / ".execution_memory"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for(self, robot_id: str) -> Path:
        safe_robot_id = require_safe_identifier(robot_id, field_name="robot_id")
        return self.store_dir / f"{safe_robot_id}.jsonl"

    def record(self, entry: dict[str, Any]) -> None:
        """Appends one real record. `entry["task"]["robot_id"]` is required (it
        picks the per-robot file); the rest is caller-defined, expected to follow
        the task/plan/execution shape this module's docstring describes."""
        if not isinstance(entry, dict):
            raise TypeError("entry must be a dictionary")
        robot_id = (entry.get("task") or {}).get("robot_id")
        if not robot_id:
            raise ValueError("entry['task']['robot_id'] is required to record an execution")
        path = self._path_for(robot_id)
        record = dict(entry)
        record.setdefault("timestamp", time.time())
        line = json.dumps(record, allow_nan=False, separators=(",", ":"))
        if len(line.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError(f"execution record exceeds the {MAX_RECORD_BYTES}-byte limit")
        with self._lock, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def query(
        self, action: str | None = None, robot_id: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Real records matching the filters, most recent first. Reads every
        per-robot file when robot_id isn't given -- fine at this scale; no SQLite
        needed for a local, single-machine history (REDESIGN.md §10)."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {MAX_QUERY_LIMIT}")
        paths = [self._path_for(robot_id)] if robot_id else sorted(self.store_dir.glob("*.jsonl"))
        records: list[dict[str, Any]] = []
        with self._lock:
            for path in paths:
                if not path.exists():
                    continue
                with path.open("r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if len(line.encode("utf-8")) > MAX_RECORD_BYTES + 1:
                            logger.warning("Skipping oversized execution record in %s line %d", path, line_number)
                            continue
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = loads_strict(line)
                        except json.JSONDecodeError:
                            logger.warning("Skipping corrupt execution record in %s line %d", path, line_number)
                            continue
                        if not isinstance(record, dict):
                            logger.warning("Skipping non-object execution record in %s line %d", path, line_number)
                            continue
                        if action is not None and (record.get("task") or {}).get("action") != action:
                            continue
                        records.append(record)
        records.sort(key=lambda r: r.get("timestamp", 0.0), reverse=True)
        return records[:limit]

    def success_rate(self, action: str, robot_id: str) -> float | None:
        """Real ratio from real records; None (never 0.0) when there's no history
        yet, so a caller can't mistake "no data" for "always fails"."""
        records = self.query(action=action, robot_id=robot_id, limit=10_000)
        if not records:
            return None
        successes = sum(1 for r in records if (r.get("execution") or {}).get("success"))
        return successes / len(records)

    def recovery_action_success_rate(self, failure_mode: str, action: str, robot_id: str) -> float | None:
        """Real historical signal for runtime/recovery.py's case-based recovery
        (item 7): among real recorded runs whose execution.recovery_attempts
        included this (failure_mode, action) pair, what fraction of those runs
        ultimately succeeded? Correlational -- the run succeeded *after* trying
        this action, possibly among others -- not a controlled causal measurement.
        Stated plainly here rather than oversold as more rigorous than it is.
        None (not 0.0) when no matching record exists."""
        records = self.query(robot_id=robot_id, limit=10_000)
        relevant = [
            r for r in records
            if any(
                a.get("failure_mode") == failure_mode and a.get("action") == action
                for a in (r.get("execution") or {}).get("recovery_attempts", [])
            )
        ]
        if not relevant:
            return None
        successes = sum(1 for r in relevant if (r.get("execution") or {}).get("success"))
        return successes / len(relevant)
