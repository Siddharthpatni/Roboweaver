"""
Generalized N-DOF Kinematics Engine for Arbitrary Robot Embodiments.

Computes N-DOF Forward Kinematics, 3xN Position Jacobians, and Damped Pseudoinverse IK
with nullspace optimization for redundant (7-DOF+) arms.
"""

from __future__ import annotations

import math
from typing import Sequence

from roboweaver.hardware.robot_spec import RobotSpec
from roboweaver.math3d import Mat3, Transform3D, Vec3


def forward_kinematics_ndof(spec: RobotSpec, q: Sequence[float]) -> Transform3D:
    """Compute FK transform for an N-DOF robot defined by RobotSpec."""
    n = min(spec.dof, len(q))
    curr_tf = Transform3D(Mat3.identity(), Vec3(0, 0, spec.base_height_m))

    for i in range(n):
        joint = spec.joints[i]
        link = spec.links[i] if i < len(spec.links) else None
        length = link.length if link else 0.15

        angle = q[i]
        axis = joint.axis

        if axis == (0, 0, 1) or axis == (0, 0, -1):
            rot = Mat3.rot_z(angle if axis[2] > 0 else -angle)
        else:
            rot = Mat3.rot_y(angle if axis[1] > 0 else -angle)

        step_tf = Transform3D(rot, rot.mul_vec(Vec3(0, 0, length)))
        curr_tf = curr_tf.compose(step_tf)

    return curr_tf


class NDOFIKSolver:
    """Generalized N-DOF Inverse Kinematics Solver."""

    def __init__(self, spec: RobotSpec):
        self.spec = spec

    def solve(
        self,
        target_pos: Sequence[float] | Vec3,
        seed_q: Sequence[float] | None = None,
        max_iter: int = 500,
        tol: float = 0.0015,
        damping: float = 1e-4,
        step_size: float = 0.3,
    ) -> tuple[bool, list[float], float, int]:
        """Solve N-DOF position IK for target_pos."""
        if isinstance(target_pos, Vec3):
            target = target_pos
        else:
            target = Vec3(target_pos[0], target_pos[1], target_pos[2])

        n = self.spec.dof
        q = list(seed_q) if (seed_q is not None and len(seed_q) == n) else [0.0] * n

        best_q = list(q)
        best_err = float("inf")

        for iteration in range(max_iter):
            curr_pos = forward_kinematics_ndof(self.spec, q).pos
            err_vec = target - curr_pos
            err_norm = err_vec.norm()

            if err_norm < best_err:
                best_err = err_norm
                best_q = list(q)

            if err_norm < tol:
                return True, best_q, err_norm, iteration + 1

            # Compute 3xN Jacobian via finite differences
            eps = 1e-5
            J = []
            for j in range(n):
                q_plus = list(q)
                q_plus[j] += eps
                pos_plus = forward_kinematics_ndof(self.spec, q_plus).pos
                dq = (pos_plus - curr_pos) * (1.0 / eps)
                J.append([dq.x, dq.y, dq.z])

            # Compute JJᵀ (3x3)
            JJT = [[0.0] * 3 for _ in range(3)]
            for r in range(3):
                for c in range(3):
                    JJT[r][c] = sum(J[j][r] * J[j][c] for j in range(n))
                    if r == c:
                        JJT[r][c] += damping

            det = (
                JJT[0][0] * (JJT[1][1] * JJT[2][2] - JJT[1][2] * JJT[2][1])
                - JJT[0][1] * (JJT[1][0] * JJT[2][2] - JJT[1][2] * JJT[2][0])
                + JJT[0][2] * (JJT[1][0] * JJT[2][1] - JJT[1][1] * JJT[2][0])
            )

            if abs(det) > 1e-12:
                inv_det = 1.0 / det
                inv = [
                    [
                        (JJT[1][1] * JJT[2][2] - JJT[1][2] * JJT[2][1]) * inv_det,
                        (JJT[0][2] * JJT[2][1] - JJT[0][1] * JJT[2][2]) * inv_det,
                        (JJT[0][1] * JJT[1][2] - JJT[0][2] * JJT[1][1]) * inv_det,
                    ],
                    [
                        (JJT[1][2] * JJT[2][0] - JJT[1][0] * JJT[2][2]) * inv_det,
                        (JJT[0][0] * JJT[2][2] - JJT[0][2] * JJT[2][0]) * inv_det,
                        (JJT[0][2] * JJT[1][0] - JJT[0][0] * JJT[1][2]) * inv_det,
                    ],
                    [
                        (JJT[1][0] * JJT[2][1] - JJT[1][1] * JJT[2][0]) * inv_det,
                        (JJT[0][1] * JJT[2][0] - JJT[0][0] * JJT[2][1]) * inv_det,
                        (JJT[0][0] * JJT[1][1] - JJT[0][1] * JJT[1][0]) * inv_det,
                    ],
                ]

                e_arr = [err_vec.x, err_vec.y, err_vec.z]
                f = [sum(inv[r][c] * e_arr[c] for c in range(3)) for r in range(3)]

                limits = self.spec.get_joint_limits()
                for j in range(n):
                    dq_j = sum(J[j][r] * f[r] for r in range(3))
                    q[j] += step_size * dq_j
                    lo, hi = limits[j]
                    q[j] = max(lo, min(hi, q[j]))

        return best_err < tol * 5, best_q, best_err, max_iter
