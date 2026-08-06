"""
Tests for RobotSpec.validate() and its enforcement at registry import time
(src/roboweaver/hardware/robot_spec.py, registry_robots.py).

This exists because of a real bug: Pepper was registered with dof=17 but only
5 LinkSpecs. forward_kinematics_ndof() pairs joints[i] with links[i]
positionally, so a wheel joint silently borrowed base_link's length, the hip
joint borrowed l_arm_link's, and the remaining 12 joints all fell back to a
fabricated 0.15m default -- yet SkillCompiler('pepper').compile(...) and the
IK solver both "succeeded" without ever surfacing that the geometry driving
them was nonsense. These tests lock in the fix and the guard that now catches
this class of bug for every registry entry before a single request can reach it.
"""

from __future__ import annotations

import pytest

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY, distinct_robot_specs, get_robot_spec
from roboweaver.hardware.robot_spec import JointSpec, LinkSpec, RobotSpec


def _minimal_spec(**overrides) -> RobotSpec:
    defaults = dict(
        id="test_robot",
        name="Test Robot",
        manufacturer="Test",
        dof=2,
        payload_capacity_kg=1.0,
        max_reach_m=0.5,
        base_height_m=0.1,
        joints=[
            JointSpec("j1", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 10.0),
            JointSpec("j2", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 10.0),
        ],
        links=[
            LinkSpec("l1", 0.2, 1.0),
            LinkSpec("l2", 0.2, 1.0),
        ],
    )
    defaults.update(overrides)
    return RobotSpec(**defaults)


def test_well_formed_spec_has_no_violations():
    assert _minimal_spec().validate() == []


@pytest.mark.parametrize("robot_id", sorted(ROBOT_REGISTRY))
def test_every_registered_robot_is_valid(robot_id):
    """The exact check that failed for Pepper before the fix -- run for every
    entry so a future addition with the same shape of bug is caught here,
    not discovered by chance while auditing FK output by hand."""
    problems = ROBOT_REGISTRY[robot_id].validate()
    assert problems == [], f"{robot_id}: {problems}"


def test_distinct_profiles_do_not_expose_aliases_as_duplicate_robots():
    profiles = distinct_robot_specs()
    ids = [profile.id for profile in profiles]
    assert len(ids) == len(set(ids))
    assert len(profiles) < len(ROBOT_REGISTRY)


def test_pepper_has_one_link_per_joint():
    """The specific bug: dof=17 must now be backed by 17 real links, not 5."""
    spec = get_robot_spec("pepper")
    assert spec.dof == 17
    assert len(spec.links) >= spec.dof


def test_pepper_joints_no_longer_share_mismatched_links():
    """Before the fix, index-based pairing gave wheel_fl the *torso's* link
    entry and 12 joints fell back to a shared fabricated length. Every joint
    must now have its own distinctly-named link."""
    spec = get_robot_spec("pepper")
    link_names = [spec.links[i].name for i in range(spec.dof)]
    assert len(link_names) == len(set(link_names)), "duplicate/reused link entries"
    # No joint should be silently defaulting via the "not enough links" path.
    assert len(spec.links) >= spec.dof


def test_too_few_links_is_detected():
    spec = _minimal_spec(dof=3, joints=[
        JointSpec("j1", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 10.0),
        JointSpec("j2", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 10.0),
        JointSpec("j3", "revolute", (0, 0, 1), -1.0, 1.0, 1.0, 10.0),
    ])  # links list still has only 2 entries from the default
    problems = spec.validate()
    assert any("links declared for dof" in p for p in problems)


def test_inverted_joint_limits_are_detected():
    spec = _minimal_spec()
    spec.joints[0] = JointSpec("j1", "revolute", (0, 0, 1), 1.0, -1.0, 1.0, 10.0)
    problems = spec.validate()
    assert any("lower_limit" in p and "upper_limit" in p for p in problems)


def test_zero_velocity_is_detected():
    spec = _minimal_spec()
    spec.joints[0] = JointSpec("j1", "revolute", (0, 0, 1), -1.0, 1.0, 0.0, 10.0)
    assert any("max_velocity" in p for p in spec.validate())


def test_zero_axis_vector_is_detected():
    spec = _minimal_spec()
    spec.joints[0] = JointSpec("j1", "revolute", (0, 0, 0), -1.0, 1.0, 1.0, 10.0)
    assert any("zero vector" in p for p in spec.validate())


def test_nonpositive_payload_is_detected():
    assert any("payload_capacity_kg" in p for p in _minimal_spec(payload_capacity_kg=0).validate())


def test_nonpositive_link_mass_is_detected():
    spec = _minimal_spec()
    spec.links[0] = LinkSpec("l1", 0.2, 0.0)
    assert any("mass must be positive" in p for p in spec.validate())


def test_registry_import_fails_loudly_on_a_broken_spec():
    """Reproduces the exact failure mode the fix guards against, without
    depending on the real registry staying broken: a fresh dict shaped like
    the original Pepper bug must raise at the same point _validate_registry()
    checks the real one."""
    from roboweaver.hardware.registry_robots import _validate_registry

    broken = _minimal_spec(id="broken", dof=5)  # 5 dof, only 2 links
    original = dict(ROBOT_REGISTRY)
    ROBOT_REGISTRY["broken_test_entry"] = broken
    try:
        with pytest.raises(ValueError, match="invalid RobotSpec"):
            _validate_registry()
    finally:
        ROBOT_REGISTRY.clear()
        ROBOT_REGISTRY.update(original)
