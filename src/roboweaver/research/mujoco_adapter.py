"""Real headless MuJoCo physics rollout for validated research embodiments.

This module never executes model-authored code. It only reads the strictly
validated numeric fields of an :class:`ExperimentSpec` (link/joint geometry,
mass, limits) and compiles them into an MJCF model. Actuation during the
rollout is a deterministic bounded synthetic signal, not a learned policy;
see ``docs`` / MILESTONES.md for that boundary.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from roboweaver.research.experiments import ExperimentSpec

try:
    import mujoco
    import numpy as np

    MUJOCO_AVAILABLE = True
    MUJOCO_VERSION = mujoco.__version__
except ImportError:  # pragma: no cover - exercised where mujoco is absent
    mujoco = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    MUJOCO_AVAILABLE = False
    MUJOCO_VERSION = None

_SYNTHETIC_ACTUATION_FRACTION = 0.2
_JOINT_DAMPING = 0.4
_GAP_M = 0.02


def _geom_size(shape: str, size_m: tuple[float, float, float]) -> tuple[str, str]:
    x, y, z = size_m
    if shape == "box":
        return "box", f"{x / 2:.4f} {y / 2:.4f} {z / 2:.4f}"
    if shape == "sphere":
        return "sphere", f"{x / 2:.4f}"
    return "cylinder" if shape == "cylinder" else "capsule", f"{x / 2:.4f} {z / 2:.4f}"


def _half_extent(link_by_name: dict[str, Any], name: str) -> float:
    return link_by_name[name].size_m[2] / 2


def _children_by_parent(spec: ExperimentSpec) -> dict[str, list]:
    children: dict[str, list] = {}
    for joint in spec.joints:
        children.setdefault(joint.parent, []).append(joint)
    return children


def _root_link_name(spec: ExperimentSpec) -> str:
    child_names = {joint.child for joint in spec.joints}
    roots = [link.name for link in spec.links if link.name not in child_names]
    return roots[0] if roots else spec.links[0].name


def _add_body(parent_xml: ET.Element, link_name: str, pos: tuple[float, float, float],
              joint: Any | None, spec: ExperimentSpec, link_by_name: dict[str, Any],
              children: dict[str, list], actuators: ET.Element) -> None:
    link = link_by_name[link_name]
    body = ET.SubElement(parent_xml, "body", {
        "name": link_name,
        "pos": f"{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f}",
    })
    if joint is not None and joint.joint_type != "fixed":
        joint_attrs = {
            "name": joint.name,
            "type": "slide" if joint.joint_type == "prismatic" else "hinge",
            "axis": " ".join(f"{v:.4f}" for v in joint.axis),
            "damping": f"{_JOINT_DAMPING}",
        }
        if joint.joint_type != "continuous":
            joint_attrs["limited"] = "true"
            joint_attrs["range"] = f"{joint.lower:.4f} {joint.upper:.4f}"
        else:
            joint_attrs["limited"] = "false"
        ET.SubElement(body, "joint", joint_attrs)
        ET.SubElement(actuators, "motor", {
            "joint": joint.name,
            "gear": "1",
            "ctrlrange": f"{-joint.effort:.4f} {joint.effort:.4f}",
        })
    geom_type, size = _geom_size(link.shape, link.size_m)
    ET.SubElement(body, "geom", {"type": geom_type, "size": size, "mass": f"{link.mass_kg:.4f}"})
    kids = children.get(link_name, [])
    count = len(kids)
    parent_half_xy = (link.size_m[0] + link.size_m[1]) / 4
    for index, child_joint in enumerate(kids):
        child_half = _half_extent(link_by_name, child_joint.child)
        dz = link.size_m[2] / 2 + child_half + _GAP_M
        if count == 1:
            dx = dy = 0.0
        else:
            angle = 2 * math.pi * index / count
            lateral = parent_half_xy + 0.05
            dx, dy = lateral * math.cos(angle), lateral * math.sin(angle)
        _add_body(body, child_joint.child, (dx, dy, dz), child_joint, spec, link_by_name, children, actuators)


def _estimate_drop_height(spec: ExperimentSpec, link_by_name: dict[str, Any], children: dict[str, list]) -> float:
    root = _root_link_name(spec)

    def depth(name: str) -> float:
        kids = children.get(name, [])
        if not kids:
            return _half_extent(link_by_name, name)
        return _half_extent(link_by_name, name) + max(
            _half_extent(link_by_name, kid.child) + depth(kid.child) for kid in kids
        )

    return max(1.0, min(depth(root) + 1.0, 50.0))


def build_mjcf(spec: ExperimentSpec) -> str:
    """Compile a validated ExperimentSpec into MJCF the way the URDF export
    is compiled from the same numeric fields; used only for physics rollout."""
    link_by_name = {link.name: link for link in spec.links}
    children = _children_by_parent(spec)
    root_name = _root_link_name(spec)
    drop_height = _estimate_drop_height(spec, link_by_name, children)

    mujoco_el = ET.Element("mujoco", {"model": spec.name})
    ET.SubElement(mujoco_el, "compiler", {"angle": "radian"})
    ET.SubElement(mujoco_el, "option", {"timestep": "0.002"})
    worldbody = ET.SubElement(mujoco_el, "worldbody")
    ET.SubElement(worldbody, "light", {"pos": "0 0 4", "dir": "0 0 -1"})
    ET.SubElement(worldbody, "geom", {"name": "floor", "type": "plane", "size": "20 20 0.1"})
    root_body = ET.SubElement(worldbody, "body", {
        "name": root_name, "pos": f"0 0 {drop_height:.4f}",
    })
    ET.SubElement(root_body, "freejoint")
    root_link = link_by_name[root_name]
    geom_type, size = _geom_size(root_link.shape, root_link.size_m)
    ET.SubElement(root_body, "geom", {"type": geom_type, "size": size, "mass": f"{root_link.mass_kg:.4f}"})
    actuators = ET.SubElement(mujoco_el, "actuator")
    kids = children.get(root_name, [])
    count = len(kids)
    parent_half_xy = (root_link.size_m[0] + root_link.size_m[1]) / 4
    for index, child_joint in enumerate(kids):
        child_half = _half_extent(link_by_name, child_joint.child)
        dz = root_link.size_m[2] / 2 + child_half + _GAP_M
        if count == 1:
            dx = dy = 0.0
        else:
            angle = 2 * math.pi * index / count
            lateral = parent_half_xy + 0.05
            dx, dy = lateral * math.cos(angle), lateral * math.sin(angle)
        _add_body(root_body, child_joint.child, (dx, dy, dz), child_joint, spec, link_by_name, children, actuators)
    if len(actuators) == 0:
        mujoco_el.remove(actuators)
    ET.indent(mujoco_el, space="  ")
    return ET.tostring(mujoco_el, encoding="unicode", xml_declaration=True) + "\n"


@dataclass(frozen=True)
class PhysicsRolloutResult:
    status: str
    mujoco_version: str | None
    steps_requested: int
    steps_executed: int
    sim_time_s: float
    wall_time_s: float
    numerically_stable: bool
    root_height_start_m: float | None
    root_height_end_m: float | None
    max_contacts_observed: int
    actuated_joints: int
    model_bodies: int
    max_actuator_torque_applied: float
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mujoco_version": self.mujoco_version,
            "steps_requested": self.steps_requested,
            "steps_executed": self.steps_executed,
            "sim_time_s": self.sim_time_s,
            "wall_time_s": self.wall_time_s,
            "numerically_stable": self.numerically_stable,
            "root_height_start_m": self.root_height_start_m,
            "root_height_end_m": self.root_height_end_m,
            "max_contacts_observed": self.max_contacts_observed,
            "actuated_joints": self.actuated_joints,
            "model_bodies": self.model_bodies,
            "max_actuator_torque_applied": self.max_actuator_torque_applied,
            "error": self.error,
            "note": (
                "Actuation is a deterministic bounded synthetic signal for morphology "
                "validation, not a trained or learned control policy."
            ),
        }


def _unavailable(reason: str) -> PhysicsRolloutResult:
    return PhysicsRolloutResult(
        status=reason, mujoco_version=None, steps_requested=0, steps_executed=0,
        sim_time_s=0.0, wall_time_s=0.0, numerically_stable=False,
        root_height_start_m=None, root_height_end_m=None, max_contacts_observed=0,
        actuated_joints=0, model_bodies=0, max_actuator_torque_applied=0.0, error=None,
    )


def run_physics_rollout(spec: ExperimentSpec, max_steps: int = 600, seed: int = 0) -> PhysicsRolloutResult:
    """Run a real, deterministic, bounded MuJoCo rollout of a validated embodiment.

    Never runs model-authored code; only reads validated numeric spec fields.
    """
    if not MUJOCO_AVAILABLE:
        return _unavailable("unavailable_mujoco_not_installed")
    if max_steps < 1 or max_steps > 20_000:
        raise ValueError("max_steps must be between 1 and 20000.")
    try:
        mjcf = build_mjcf(spec)
        model = mujoco.MjModel.from_xml_string(mjcf)
    except Exception as exc:  # noqa: BLE001 - MuJoCo raises plain Exception/ValueError on bad models
        return PhysicsRolloutResult(
            status="model_compile_failed", mujoco_version=MUJOCO_VERSION, steps_requested=max_steps,
            steps_executed=0, sim_time_s=0.0, wall_time_s=0.0, numerically_stable=False,
            root_height_start_m=None, root_height_end_m=None, max_contacts_observed=0,
            actuated_joints=0, model_bodies=0, max_actuator_torque_applied=0.0, error=str(exc)[:300],
        )
    data = mujoco.MjData(model)
    rng = random.Random(seed)
    root_z_start = float(data.qpos[2]) if model.nq >= 3 else 0.0
    max_torque = 0.0
    max_contacts = 0
    stable = True
    executed = 0
    wall_start = time.perf_counter()
    for _ in range(max_steps):
        if model.nu:
            ctrl = [
                rng.uniform(-1.0, 1.0) * model.actuator_ctrlrange[i][1] * _SYNTHETIC_ACTUATION_FRACTION
                for i in range(model.nu)
            ]
            data.ctrl[:] = ctrl
            max_torque = max(max_torque, max(abs(value) for value in ctrl))
        mujoco.mj_step(model, data)
        executed += 1
        max_contacts = max(max_contacts, int(data.ncon))
        if not (bool(np.all(np.isfinite(data.qpos))) and bool(np.all(np.isfinite(data.qvel)))):
            stable = False
            break
    wall_time = time.perf_counter() - wall_start
    return PhysicsRolloutResult(
        status="executed" if stable else "diverged_numerically",
        mujoco_version=MUJOCO_VERSION,
        steps_requested=max_steps,
        steps_executed=executed,
        sim_time_s=round(executed * float(model.opt.timestep), 6),
        wall_time_s=round(wall_time, 4),
        numerically_stable=stable,
        root_height_start_m=round(root_z_start, 4),
        root_height_end_m=round(float(data.qpos[2]), 4) if stable and model.nq >= 3 else None,
        max_contacts_observed=max_contacts,
        actuated_joints=int(model.nu),
        model_bodies=int(model.nbody),
        max_actuator_torque_applied=round(max_torque, 4),
        error=None,
    )
