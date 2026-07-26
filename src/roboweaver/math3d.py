"""
Pure Python 3D Math Engine for RoboWeaver.

Provides Vector3, Matrix3x3, and Transform3D classes with full 3D spatial
algebra (dot product, cross product, matrix multiplication, forward/inverse
transforms, and point transformations) without external dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Vec3:
    """3D Vector representation."""
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def norm(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalize(self) -> Vec3:
        n = self.norm()
        if n < 1e-9:
            return Vec3(0, 0, 0)
        return Vec3(self.x / n, self.y / n, self.z / n)

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Mat3:
    """3x3 Rotation Matrix."""
    def __init__(self, data: list[list[float]] | None = None):
        if data is None:
            self.m = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        else:
            self.m = data

    @staticmethod
    def identity() -> Mat3:
        return Mat3()

    @staticmethod
    def rot_x(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return Mat3([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])

    @staticmethod
    def rot_y(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return Mat3([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])

    @staticmethod
    def rot_z(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return Mat3([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])

    def __matmul__(self, other: Mat3) -> Mat3:
        res = [[0.0] * 3 for _ in range(3)]
        for i in range(3):
            for j in range(3):
                res[i][j] = sum(self.m[i][k] * other.m[k][j] for k in range(3))
        return Mat3(res)

    def mul_vec(self, v: Vec3) -> Vec3:
        return Vec3(
            self.m[0][0] * v.x + self.m[0][1] * v.y + self.m[0][2] * v.z,
            self.m[1][0] * v.x + self.m[1][1] * v.y + self.m[1][2] * v.z,
            self.m[2][0] * v.x + self.m[2][1] * v.y + self.m[2][2] * v.z,
        )

    def transpose(self) -> Mat3:
        return Mat3([[self.m[j][i] for j in range(3)] for i in range(3)])


@dataclass
class Transform3D:
    """Rigid 3D Body Transformation (Rotation + Translation)."""
    rot: Mat3
    pos: Vec3

    @staticmethod
    def identity() -> Transform3D:
        return Transform3D(Mat3.identity(), Vec3(0, 0, 0))

    def apply(self, point: Vec3) -> Vec3:
        """Transform a 3D point."""
        return self.rot.mul_vec(point) + self.pos

    def compose(self, child_tf: Transform3D) -> Transform3D:
        """Compose parent transform with child transform."""
        new_rot = self.rot @ child_tf.rot
        new_pos = self.pos + self.rot.mul_vec(child_tf.pos)
        return Transform3D(new_rot, new_pos)
