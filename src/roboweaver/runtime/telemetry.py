"""
Telemetry Engine — records 100Hz real-time execution telemetry and metrics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TelemetryFrame:
    timestamp: float
    step: int
    task_description: str
    ee_position: tuple[float, float, float]
    joint_angles: list[float]
    gripper_state: str
    is_grasped: bool


class TelemetryRecorder:
    """Records high-frequency execution metrics."""

    def __init__(self):
        self.frames: list[TelemetryFrame] = []

    def record(
        self,
        timestamp: float,
        step: int,
        task_description: str,
        ee_pos: tuple[float, float, float],
        joint_angles: list[float],
        gripper_state: str,
        is_grasped: bool,
    ) -> None:
        frame = TelemetryFrame(
            timestamp=timestamp,
            step=step,
            task_description=task_description,
            ee_position=ee_pos,
            joint_angles=joint_angles,
            gripper_state=gripper_state,
            is_grasped=is_grasped,
        )
        self.frames.append(frame)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [asdict(f) for f in self.frames]
