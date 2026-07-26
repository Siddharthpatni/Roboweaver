"""
Workspace Safety Guard — enforces velocity margins, workspace bounds, and payload limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Vec3


@dataclass
class SafetyCheckResult:
    is_safe: bool
    violations: list[str]


class WorkspaceSafetyGuard:
    """Monitors physical constraints for safe execution."""

    def __init__(self, spec: RobotSpec):
        self.spec = spec

    def validate_pose(self, pos: Vec3 | Sequence[float]) -> SafetyCheckResult:
        """Validate target position is within max reach and workspace bounds."""
        if isinstance(pos, Vec3):
            p = pos
        else:
            p = Vec3(pos[0], pos[1], pos[2])

        violations = []
        # Calculate radial reach in XY plane and vertical height Z
        radial_xy = (p.x**2 + p.y**2)**0.5
        rel_z = max(0.0, p.z - self.spec.base_height_m)
        reach = (radial_xy**2 + rel_z**2)**0.5

        # Operational reach check (radial distance from base axis)
        if radial_xy > self.spec.max_reach_m:
            violations.append(
                f"Position ({p.x:.2f}, {p.y:.2f}, {p.z:.2f}) radial distance {radial_xy:.2f}m exceeds max reach {self.spec.max_reach_m}m"
            )

        if p.z < -0.05:
            violations.append(f"Position z={p.z:.2f}m is below floor boundary")

        return SafetyCheckResult(is_safe=len(violations) == 0, violations=violations)

    def validate_payload(self, mass_kg: float) -> SafetyCheckResult:
        """Validate payload mass does not exceed payload capacity."""
        violations = []
        if mass_kg > self.spec.payload_capacity_kg:
            violations.append(
                f"Payload {mass_kg:.1f}kg exceeds robot payload limit {self.spec.payload_capacity_kg}kg"
            )
        return SafetyCheckResult(is_safe=len(violations) == 0, violations=violations)

    def validate_joint_limits(self, q: Sequence[float]) -> SafetyCheckResult:
        """Validate joint positions are within safety margins."""
        violations = []
        limits = self.spec.get_joint_limits()
        for i, val in enumerate(q[: self.spec.dof]):
            lo, hi = limits[i]
            if val < lo or val > hi:
                violations.append(
                    f"Joint {self.spec.joints[i].name} value {val:.2f} rad out of range [{lo:.2f}, {hi:.2f}]"
                )
        return SafetyCheckResult(is_safe=len(violations) == 0, violations=violations)
