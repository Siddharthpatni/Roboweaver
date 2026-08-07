"""Serializable collision scene primitives."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from roboweaver.math3d import Vec3


@dataclass(frozen=True)
class Sphere:
    id: str
    center: Vec3
    radius_m: float

    def __post_init__(self) -> None:
        if not self.id.strip() or self.radius_m <= 0 or not math.isfinite(self.radius_m):
            raise ValueError("sphere requires an id and a positive finite radius")

    def contains_inflated(self, point: Vec3, inflation_m: float) -> bool:
        return (point - self.center).norm() <= self.radius_m + inflation_m

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "sphere", "id": self.id,
            "center_m": [self.center.x, self.center.y, self.center.z],
            "radius_m": self.radius_m,
        }


@dataclass(frozen=True)
class AABB:
    id: str
    minimum: Vec3
    maximum: Vec3

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("AABB requires an id")
        if not (
            self.minimum.x < self.maximum.x
            and self.minimum.y < self.maximum.y
            and self.minimum.z < self.maximum.z
        ):
            raise ValueError("AABB minimum must be strictly below maximum on every axis")

    def contains_inflated(self, point: Vec3, inflation_m: float) -> bool:
        return (
            self.minimum.x - inflation_m <= point.x <= self.maximum.x + inflation_m
            and self.minimum.y - inflation_m <= point.y <= self.maximum.y + inflation_m
            and self.minimum.z - inflation_m <= point.z <= self.maximum.z + inflation_m
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "aabb", "id": self.id,
            "minimum_m": [self.minimum.x, self.minimum.y, self.minimum.z],
            "maximum_m": [self.maximum.x, self.maximum.y, self.maximum.z],
        }


Obstacle = Sphere | AABB


@dataclass(frozen=True)
class Scene:
    frame_id: str
    obstacles: tuple[Obstacle, ...]
    resolution_m: float = 0.04

    def __post_init__(self) -> None:
        object.__setattr__(self, "obstacles", tuple(self.obstacles))
        if not self.frame_id.strip():
            raise ValueError("scene frame_id is required")
        if self.resolution_m <= 0 or not math.isfinite(self.resolution_m):
            raise ValueError("scene resolution_m must be positive and finite")
        ids = [item.id for item in self.obstacles]
        if len(ids) != len(set(ids)):
            raise ValueError("scene obstacle ids must be unique")

    def collides(self, point: Vec3, inflation_m: float) -> bool:
        return any(item.contains_inflated(point, inflation_m) for item in self.obstacles)

    def digest(self) -> str:
        payload = {
            "frame_id": self.frame_id,
            "resolution_m": self.resolution_m,
            "obstacles": [item.to_dict() for item in self.obstacles],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        obstacles: list[Obstacle] = []
        for item in data.get("obstacles", []):
            if item.get("type") == "sphere":
                obstacles.append(Sphere(
                    str(item["id"]), Vec3(*map(float, item["center_m"])), float(item["radius_m"]),
                ))
            elif item.get("type") == "aabb":
                obstacles.append(AABB(
                    str(item["id"]),
                    Vec3(*map(float, item["minimum_m"])),
                    Vec3(*map(float, item["maximum_m"])),
                ))
            else:
                raise ValueError(f"unknown scene obstacle type {item.get('type')!r}")
        return cls(
            frame_id=str(data.get("frame_id", "robot_base")),
            obstacles=tuple(obstacles),
            resolution_m=float(data.get("resolution_m", 0.04)),
        )
