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

    def validate(self) -> list[str]:
        """Returns every structural problem found, empty if none.

        Every consumer of this dataclass -- forward_kinematics_ndof,
        NDOFIKSolver, urdf_gen.py, the IR safety checker -- walks
        `spec.joints[:dof]` and `spec.links[i] if i < len(spec.links) else
        None` in lockstep. That silent fallback is what let a real bug ship
        undetected: Pepper (dof=17) had only 5 LinkSpecs, so its FK/IK/URDF
        paired a wheel joint with `base_link`'s length, the hip with
        `l_arm_link`'s, and the remaining 12 joints all fell back to the same
        fabricated 0.15m -- a physically meaningless chain that nonetheless
        "solved" IK and compiled skills without any error. This check is
        called for every registry entry at import time (registry_robots.py)
        specifically so a spec shaped like that fails loudly before a single
        request ever reaches it, rather than being caught by chance the next
        time someone happens to audit FK output by hand.
        """
        problems: list[str] = []
        if self.dof <= 0:
            problems.append(f"dof must be positive, got {self.dof}")
        if len(self.joints) < self.dof:
            problems.append(f"only {len(self.joints)} joints declared for dof={self.dof}")
        if len(self.links) < self.dof:
            problems.append(f"only {len(self.links)} links declared for dof={self.dof} "
                             f"-- FK/IK/URDF index joints[i] against links[i] in lockstep, "
                             f"so a shortfall here silently mispairs or fabricates geometry")
        if self.payload_capacity_kg <= 0:
            problems.append(f"payload_capacity_kg must be positive, got {self.payload_capacity_kg}")
        if self.max_reach_m <= 0:
            problems.append(f"max_reach_m must be positive, got {self.max_reach_m}")

        for j in self.joints[: self.dof]:
            if j.lower_limit > j.upper_limit:
                problems.append(f"joint '{j.name}': lower_limit ({j.lower_limit}) > upper_limit ({j.upper_limit})")
            if j.max_velocity <= 0:
                problems.append(f"joint '{j.name}': max_velocity must be positive, got {j.max_velocity}")
            if j.max_effort <= 0:
                problems.append(f"joint '{j.name}': max_effort must be positive, got {j.max_effort}")
            if j.axis == (0.0, 0.0, 0.0):
                problems.append(f"joint '{j.name}': axis is the zero vector -- no rotation/translation is defined")

        for link in self.links[: self.dof]:
            if link.length < 0:
                problems.append(f"link '{link.name}': negative length ({link.length})")
            if link.mass <= 0:
                problems.append(f"link '{link.name}': mass must be positive, got {link.mass}")

        return problems
