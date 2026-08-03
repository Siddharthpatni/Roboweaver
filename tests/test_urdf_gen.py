"""
Tests for RobotSpec -> URDF / STL generation (src/roboweaver/codegen/urdf_gen.py).

The point of this module is that the emitted model is *loadable* and *physically
consistent with the spec the compiler plans against*. So the tests check exactly
that: well-formed XML, a resolvable link tree, limits that match the RobotSpec,
inertia that matches the closed form, and a byte-exact binary STL header.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET

import pytest

from roboweaver.codegen.urdf_gen import (
    _cylinder_inertia,
    _link_radius,
    export_urdf,
    generate_link_stl,
    generate_urdf,
)
from roboweaver.hardware.registry_robots import ROBOT_REGISTRY, get_robot_spec


@pytest.mark.parametrize("robot_id", sorted(ROBOT_REGISTRY))
def test_every_registry_robot_emits_wellformed_urdf(robot_id):
    """A model that does not parse is worthless -- this must hold for all robots."""
    root = ET.fromstring(generate_urdf(get_robot_spec(robot_id)))
    assert root.tag == "robot"
    assert root.findall("link"), f"{robot_id} produced no links"


@pytest.mark.parametrize("robot_id", sorted(ROBOT_REGISTRY))
def test_link_tree_is_fully_resolvable(robot_id):
    """Every joint's parent and child must name a link that actually exists,
    otherwise RViz/Gazebo reject the file at load time."""
    root = ET.fromstring(generate_urdf(get_robot_spec(robot_id)))
    declared = {link.get("name") for link in root.findall("link")}
    for joint in root.findall("joint"):
        assert joint.find("parent").get("link") in declared
        assert joint.find("child").get("link") in declared


def test_joint_limits_match_the_robot_spec():
    """The URDF must not disagree with the spec the IK solver uses -- a model
    with looser limits than the planner would license unreachable motion."""
    spec = get_robot_spec("franka_panda")
    root = ET.fromstring(generate_urdf(spec))
    joints = [j for j in root.findall("joint") if j.get("type") != "fixed"]
    assert len(joints) == spec.dof

    for i, joint_el in enumerate(joints):
        limit = joint_el.find("limit")
        assert float(limit.get("lower")) == pytest.approx(spec.joints[i].lower_limit, abs=1e-6)
        assert float(limit.get("upper")) == pytest.approx(spec.joints[i].upper_limit, abs=1e-6)
        assert float(limit.get("velocity")) == pytest.approx(spec.joints[i].max_velocity, abs=1e-6)
        assert float(limit.get("effort")) == pytest.approx(spec.joints[i].max_effort, abs=1e-6)


def test_actuated_joint_count_matches_dof():
    """Some registry entries list more joints than their declared dof (a fixed
    camera joint, say). The URDF must follow dof, as the rest of the codebase does."""
    for robot_id, spec in ROBOT_REGISTRY.items():
        root = ET.fromstring(generate_urdf(spec))
        movable = [j for j in root.findall("joint") if j.get("type") in ("revolute", "prismatic")]
        assert len(movable) == spec.dof, f"{robot_id}: {len(movable)} movable joints vs dof {spec.dof}"


def test_cylinder_inertia_matches_closed_form():
    mass, radius, length = 3.0, 0.05, 0.3
    ixx, iyy, izz = _cylinder_inertia(mass, radius, length)
    assert ixx == pytest.approx((1 / 12) * mass * (3 * radius**2 + length**2))
    assert iyy == pytest.approx(ixx)
    assert izz == pytest.approx(0.5 * mass * radius**2)


def test_every_link_declares_positive_mass_and_inertia():
    """Zero or negative inertia makes a physics engine explode on load."""
    root = ET.fromstring(generate_urdf(get_robot_spec("kuka_iiwa")))
    for link in root.findall("link"):
        inertial = link.find("inertial")
        if inertial is None:  # the zero-mass tool0 frame
            continue
        assert float(inertial.find("mass").get("value")) > 0
        inertia = inertial.find("inertia")
        for axis in ("ixx", "iyy", "izz"):
            assert float(inertia.get(axis)) > 0


def test_link_radius_is_clamped():
    assert _link_radius(0.0) >= 0.02      # a zero-length link must not vanish
    assert _link_radius(100.0) <= 0.09    # nor a long one become a barrel


def test_binary_stl_header_and_size_are_exact():
    """Binary STL is 80-byte header + uint32 count + 50 bytes per triangle.
    A wrong size silently corrupts the mesh in most loaders."""
    data = generate_link_stl(radius=0.05, length=0.3, segments=24)
    count = struct.unpack("<I", data[80:84])[0]
    assert count == 24 * 4  # two side triangles + two cap triangles per segment
    assert len(data) == 84 + count * 50


def test_generation_is_deterministic():
    """Same spec, same bytes -- so the output can be committed and diffed."""
    spec = get_robot_spec("ur5e")
    assert generate_urdf(spec) == generate_urdf(spec)


def test_export_writes_urdf_and_meshes(tmp_path):
    spec = get_robot_spec("ur5e")
    urdf_path, meshes = export_urdf(spec, tmp_path / "ur5e.urdf", with_meshes=True)

    assert urdf_path.exists() and urdf_path.stat().st_size > 0
    assert len(meshes) == spec.dof
    assert all(m.exists() and m.stat().st_size > 84 for m in meshes)

    # With meshes requested the URDF must actually reference them, not cylinders.
    text = urdf_path.read_text()
    assert "<mesh filename=" in text
    for mesh in meshes:
        assert mesh.name in text
