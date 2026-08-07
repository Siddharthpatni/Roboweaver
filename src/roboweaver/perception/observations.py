"""Validated object-pose ingestion for real perception systems.

RoboWeaver deliberately does not bundle a detector.  It accepts measured output
from camera/ROS/industrial perception processes through this provider boundary and
rejects stale, low-confidence, wrong-frame, or malformed observations before they
can influence motion lowering.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roboweaver.types import SkillIntent


class PerceptionError(ValueError):
    """Perception evidence is absent or does not satisfy the compile policy."""


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PerceptionError("observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PerceptionError("observed_at must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class PoseObservation:
    object_id: str
    object_class: str
    position_m: tuple[float, float, float]
    frame_id: str
    observed_at: str
    confidence: float
    provider_id: str
    calibration_id: str

    def validate(
        self,
        *,
        expected_frame: str = "robot_base",
        min_confidence: float = 0.75,
        max_age_s: float = 2.0,
        now: datetime | None = None,
    ) -> None:
        if not self.object_id.strip() or not self.provider_id.strip() or not self.calibration_id.strip():
            raise PerceptionError("object_id, provider_id, and calibration_id are required")
        if len(self.position_m) != 3 or not all(math.isfinite(value) for value in self.position_m):
            raise PerceptionError("position_m must contain exactly three finite values")
        if self.frame_id != expected_frame:
            raise PerceptionError(
                f"observation frame {self.frame_id!r} does not match required frame {expected_frame!r}"
            )
        if not math.isfinite(self.confidence) or not min_confidence <= self.confidence <= 1.0:
            raise PerceptionError(
                f"observation confidence {self.confidence!r} is below policy minimum {min_confidence}"
            )
        timestamp = _parse_timestamp(self.observed_at)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = (current - timestamp).total_seconds()
        if age < -0.5:
            raise PerceptionError("observation timestamp is in the future")
        if age > max_age_s:
            raise PerceptionError(
                f"observation is stale ({age:.3f}s old; maximum is {max_age_s:.3f}s)"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PoseObservation":
        position = data.get("position_m")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            raise PerceptionError("position_m must be a three-element array")
        try:
            return cls(
                object_id=str(data["object_id"]),
                object_class=str(data.get("object_class", data["object_id"])),
                position_m=tuple(float(value) for value in position),
                frame_id=str(data["frame_id"]),
                observed_at=str(data["observed_at"]),
                confidence=float(data["confidence"]),
                provider_id=str(data["provider_id"]),
                calibration_id=str(data["calibration_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PerceptionError(f"malformed pose observation: {exc}") from exc


class ObservationProvider(ABC):
    provider_id: str

    @abstractmethod
    def observe(self, object_name: str) -> PoseObservation | None:
        raise NotImplementedError


class StaticObservationProvider(ObservationProvider):
    """In-memory provider for ROS adapters, integration tests, and embedded hosts."""

    def __init__(self, observations: list[PoseObservation], provider_id: str = "static"):
        self.provider_id = provider_id
        self._observations = {item.object_id.casefold(): item for item in observations}

    def observe(self, object_name: str) -> PoseObservation | None:
        keys = {object_name.casefold(), object_name.replace("_", " ").casefold()}
        for key, observation in self._observations.items():
            if key in keys or observation.object_class.casefold() in keys:
                return observation
        return None


class JsonObservationProvider(StaticObservationProvider):
    """Read a detector/process handoff file with a top-level observations array."""

    def __init__(self, path: str | Path):
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PerceptionError(f"cannot read perception observations: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
            raise PerceptionError("perception JSON must contain an observations array")
        observations = [PoseObservation.from_dict(item) for item in payload["observations"]]
        super().__init__(observations, provider_id=f"json:{source.name}")


def apply_observation(
    intent: SkillIntent,
    provider: ObservationProvider,
    *,
    expected_frame: str = "robot_base",
    min_confidence: float = 0.75,
    max_age_s: float = 2.0,
) -> SkillIntent:
    """Resolve and attach measured pose evidence, failing closed when configured."""
    observation = provider.observe(intent.object_name)
    if observation is None:
        raise PerceptionError(
            f"provider {provider.provider_id!r} returned no observation for {intent.object_name!r}"
        )
    observation.validate(
        expected_frame=expected_frame,
        min_confidence=min_confidence,
        max_age_s=max_age_s,
    )
    parameters = dict(intent.parameters)
    parameters.update({
        "x_m": observation.position_m[0],
        "y_m": observation.position_m[1],
        "z_m": observation.position_m[2],
        "_pose_source": "perception",
        "_observation_frame": observation.frame_id,
        "_observation_timestamp": observation.observed_at,
        "_observation_confidence": observation.confidence,
        "_observation_provider": observation.provider_id,
        "_calibration_id": observation.calibration_id,
    })
    return replace(intent, parameters=parameters)
