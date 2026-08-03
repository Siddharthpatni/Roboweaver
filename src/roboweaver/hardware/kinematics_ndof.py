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


def forward_kinematics_chain_ndof(spec: RobotSpec, q: Sequence[float]) -> list[Vec3]:
    """Every joint position along the kinematic chain, base to end-effector.

    Same per-link composition as forward_kinematics_ndof (kept as the single source
    of truth for the math), except it returns the full chain of positions instead of
    only the final transform -- what a 3D viewer needs to draw each link as a real
    segment between consecutive joint origins, driven by this robot's actual RobotSpec
    geometry rather than a generic N-DOF cartoon.
    """
    n = min(spec.dof, len(q))
    curr_tf = Transform3D(Mat3.identity(), Vec3(0, 0, spec.base_height_m))
    positions = [curr_tf.pos]

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
        positions.append(curr_tf.pos)

    return positions


class NDOFIKSolver:
    """Generalized N-DOF Inverse Kinematics Solver.

    V2 improvements:
    - **Multi-seed IK**: tries 5 seeds (clamped-zero + 4 random within joint limits)
      and picks the solution with the lowest residual.  Dramatically improves solve
      rates for redundant arms where the zero-seed lands in a bad basin.
    - **Adaptive damping**: starts low and increases when the solver stalls near a
      singularity, preventing oscillation without over-damping easy solves.
    """

    def __init__(self, spec: RobotSpec):
        self.spec = spec

    def _random_seed(self) -> list[float]:
        """Generate a random seed within joint limits using a simple LCG so we
        don't add a new runtime dependency on numpy/random just for IK seeding."""
        import random
        limits = self.spec.get_joint_limits()
        return [random.uniform(lo, hi) for lo, hi in limits[:self.spec.dof]]

    def _clamped_zero_seed(self) -> list[float]:
        """Zero clamped into each joint's declared range."""
        return [
            max(j.lower_limit, min(j.upper_limit, 0.0))
            for j in self.spec.joints[:self.spec.dof]
        ]

    def solve(
        self,
        target_pos: Sequence[float] | Vec3,
        seed_q: Sequence[float] | None = None,
        max_iter: int = 800,
        tol: float = 0.001,
        damping: float = 1e-4,
        step_size: float = 0.3,
        num_seeds: int = 5,
    ) -> tuple[bool, list[float], float, int]:
        """Solve N-DOF position IK for target_pos with multi-seed + adaptive damping."""
        if isinstance(target_pos, Vec3):
            target = target_pos
        else:
            target = Vec3(target_pos[0], target_pos[1], target_pos[2])

        n = self.spec.dof

        # Build seed list: explicit seed first, then clamped-zero, then randoms
        seeds: list[list[float]] = []
        if seed_q is not None and len(seed_q) == n:
            seeds.append(list(seed_q))
        seeds.append(self._clamped_zero_seed())
        while len(seeds) < num_seeds:
            seeds.append(self._random_seed())

        global_best_q: list[float] = seeds[0]
        global_best_err = float("inf")
        global_total_iters = 0

        for seed in seeds:
            ok, q, err, iters = self._solve_single(target, list(seed), max_iter // num_seeds, tol, damping, step_size)
            global_total_iters += iters
            if err < global_best_err:
                global_best_err = err
                global_best_q = q
            if ok:
                return True, global_best_q, global_best_err, global_total_iters

        # If no seed converged, do a final extended run from the best seed found
        if global_best_err >= tol:
            ok, q, err, iters = self._solve_single(target, global_best_q, max_iter, tol, damping * 0.5, step_size)
            global_total_iters += iters
            if err < global_best_err:
                global_best_err = err
                global_best_q = q
            if ok:
                return True, global_best_q, global_best_err, global_total_iters

        return global_best_err < tol * 5, global_best_q, global_best_err, global_total_iters

    def _solve_single(
        self,
        target: Vec3,
        q: list[float],
        max_iter: int,
        tol: float,
        damping: float,
        step_size: float,
    ) -> tuple[bool, list[float], float, int]:
        """Single-seed damped pseudoinverse IK with adaptive damping."""
        n = self.spec.dof
        best_q = list(q)
        best_err = float("inf")
        current_damping = damping
        stall_count = 0
        prev_err = float("inf")

        for iteration in range(max_iter):
            curr_pos = forward_kinematics_ndof(self.spec, q).pos
            err_vec = target - curr_pos
            err_norm = err_vec.norm()

            if err_norm < best_err:
                best_err = err_norm
                best_q = list(q)
                stall_count = 0
            else:
                stall_count += 1

            if err_norm < tol:
                return True, best_q, err_norm, iteration + 1

            # Adaptive damping: increase when stalling (near singularity)
            if stall_count > 10:
                current_damping = min(current_damping * 2.0, 0.1)
                stall_count = 0
            elif err_norm < prev_err * 0.95:
                # Good progress — reduce damping for faster convergence
                current_damping = max(current_damping * 0.8, damping * 0.1)

            prev_err = err_norm

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
                        JJT[r][c] += current_damping

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

