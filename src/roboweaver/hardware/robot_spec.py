"""
Robot Hardware Specifications & Data Models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class JointSpec:
    """Specification for a robot joint."""
    name: str
    type: str  # 'revolute' or 'prismatic'
    axis: tuple[float, float, float]
    lower_limit: float  # radians or meters
    upper_limit: float  # radians or meters
    max_velocity: float  # rad/s or m/s
    max_effort: float  # Nm or N


@dataclass
class LinkSpec:
    """Specification for a robot link."""
    name: str
    length: float  # meters
    mass: float  # kg
    center_of_mass: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class RobotSpec:
    """Universal Specification for a Robot Embodiment."""
    id: str
    name: str
    manufacturer: str
    dof: int
    payload_capacity_kg: float
    max_reach_m: float
    base_height_m: float
    joints: list[JointSpec]
    links: list[LinkSpec]
    gripper_type: str = "parallel_jaw"
    has_force_torque_sensor: bool = True
    description: str = ""

    def get_joint_limits(self) -> list[tuple[float, float]]:
        return [(j.lower_limit, j.upper_limit) for j in self.joints]

    def get_max_velocities(self) -> list[float]:
        return [j.max_velocity for j in self.joints]
