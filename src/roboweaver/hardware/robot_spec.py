"""
Robot Hardware Specifications & Data Models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


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
    # The target-specific motion dialect used during lowering.  A universal
    # compiler must not pretend every embodiment is one serial manipulator.
    motion_model: str = "serial_arm"
    # Named branches map to positional joint/link indices.  Serial arms leave
    # this empty; branched embodiments (for example Pepper) declare each arm.
    kinematic_chains: dict[str, tuple[int, ...]] = field(default_factory=dict)
    # Typed model constants such as wheel radius/track width or a branch origin.
    motion_parameters: dict[str, float] = field(default_factory=dict)
    # Conservative capsule radius used by the bounded collision planner.
    collision_radius_m: float = 0.04
    # Discrete configuration-space exclusions checked against every compiled
    # waypoint. This is intentionally joint-space only; it is not a collision
    # geometry or continuous-time safety proof.
    forbidden_joint_ranges: dict[int, tuple[float, float]] = field(default_factory=dict)

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
        problems = _validate_dimensions(self)
        problems.extend(_validate_motion_model(self))
        problems.extend(_validate_joints_and_links(self))
        problems.extend(_validate_forbidden_ranges(self))
        return problems


def _validate_dimensions(spec: RobotSpec) -> list[str]:
    problems: list[str] = []
    if spec.dof <= 0:
        problems.append(f"dof must be positive, got {spec.dof}")
    if len(spec.joints) < spec.dof:
        problems.append(f"only {len(spec.joints)} joints declared for dof={spec.dof}")
    if len(spec.links) < spec.dof:
        problems.append(f"only {len(spec.links)} links declared for dof={spec.dof} "
                             f"-- FK/IK/URDF index joints[i] against links[i] in lockstep, "
                             f"so a shortfall here silently mispairs or fabricates geometry")
    if spec.payload_capacity_kg <= 0:
        problems.append(f"payload_capacity_kg must be positive, got {spec.payload_capacity_kg}")
    if spec.max_reach_m <= 0:
        problems.append(f"max_reach_m must be positive, got {spec.max_reach_m}")
    return problems


def _validate_motion_model(spec: RobotSpec) -> list[str]:
    problems: list[str] = []
    supported_motion_models = {
            "serial_arm", "holonomic_base", "differential_drive",
            "branched_humanoid", "multi_finger_hand",
    }
    if spec.motion_model not in supported_motion_models:
        problems.append(
                f"motion_model {spec.motion_model!r} is not one of "
                f"{sorted(supported_motion_models)}"
        )
    if spec.collision_radius_m <= 0 or not math.isfinite(spec.collision_radius_m):
        problems.append(
            f"collision_radius_m must be positive and finite, got {spec.collision_radius_m}"
        )

    for chain_name, indices in spec.kinematic_chains.items():
        if not chain_name.strip() or not indices:
            problems.append("kinematic chain names and index lists must be non-empty")
            continue
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < spec.dof:
                problems.append(
                    f"kinematic chain {chain_name!r} contains invalid joint index {index!r}"
                )
    if spec.motion_model == "branched_humanoid" and not spec.kinematic_chains:
        problems.append("branched_humanoid requires at least one declared kinematic chain")

    required_parameters = {
            "differential_drive": ("wheel_radius_m", "track_width_m"),
            "branched_humanoid": ("branch_base_height_m",),
    }.get(spec.motion_model, ())
    for parameter in required_parameters:
        value = spec.motion_parameters.get(parameter)
        if value is None or value <= 0 or not math.isfinite(value):
            problems.append(
                f"{spec.motion_model} requires positive finite motion parameter {parameter!r}"
            )
    return problems


def _validate_joints_and_links(spec: RobotSpec) -> list[str]:
    problems: list[str] = []
    for joint in spec.joints[: spec.dof]:
        if joint.lower_limit > joint.upper_limit:
            problems.append(f"joint '{joint.name}': lower_limit ({joint.lower_limit}) > upper_limit ({joint.upper_limit})")
        if joint.max_velocity <= 0:
            problems.append(f"joint '{joint.name}': max_velocity must be positive, got {joint.max_velocity}")
        if joint.max_effort <= 0:
            problems.append(f"joint '{joint.name}': max_effort must be positive, got {joint.max_effort}")
        if joint.axis == (0.0, 0.0, 0.0):
            problems.append(f"joint '{joint.name}': axis is the zero vector -- no rotation/translation is defined")

    for link in spec.links[: spec.dof]:
        if link.length < 0:
            problems.append(f"link '{link.name}': negative length ({link.length})")
        if link.mass <= 0:
            problems.append(f"link '{link.name}': mass must be positive, got {link.mass}")
    return problems


def _validate_forbidden_ranges(spec: RobotSpec) -> list[str]:
    problems: list[str] = []
    for joint_index, bounds in spec.forbidden_joint_ranges.items():
        if isinstance(joint_index, bool) or not isinstance(joint_index, int):
            problems.append(f"forbidden joint index must be an integer, got {joint_index!r}")
            continue
        if not 0 <= joint_index < spec.dof:
            problems.append(f"forbidden joint index {joint_index} is outside dof={spec.dof}")
            continue
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            problems.append(f"forbidden range for joint {joint_index} must contain exactly two bounds")
            continue
        lo, hi = bounds
        numeric = not isinstance(lo, bool) and not isinstance(hi, bool) and isinstance(lo, (int, float)) and isinstance(hi, (int, float))
        if not numeric:
            problems.append(f"forbidden range for joint {joint_index} must be numeric")
        elif not math.isfinite(float(lo)) or not math.isfinite(float(hi)):
            problems.append(f"forbidden range for joint {joint_index} must be finite")
        elif lo > hi:
            problems.append(f"forbidden range for joint {joint_index} is inverted ({lo} > {hi})")
    return problems
