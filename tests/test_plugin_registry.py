"""
Verification suite for the plugin registry (plugins/registry.py) and its first real
consumer, hardware/universal_driver.py -- docs/COMPILER_ROADMAP.md Phase 13.
"""

import pytest

from roboweaver.plugins import PluginRegistry
from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import (
    UniversalRobotDriver,
    ROS2HardwareBridge,
    SimulationHardwareBridge,
)


def test_register_and_get():
    print("\n[TEST 1] Testing PluginRegistry register/get round-trip...")
    reg: PluginRegistry[type] = PluginRegistry(kind="widget")

    @reg.register("foo")
    class Foo:
        pass

    assert reg.get("foo") is Foo
    assert reg.get("FOO") is Foo  # case-insensitive
    assert "foo" in reg
    assert reg.names() == ["foo"]
    print("  -> register/get round-trips, case-insensitive lookup works [PASSED]")


def test_duplicate_registration_raises():
    print("\n[TEST 2] Testing duplicate registration is refused by default...")
    reg: PluginRegistry[type] = PluginRegistry(kind="widget")
    reg.register("foo")(object)
    with pytest.raises(ValueError):
        reg.register("foo")(object)
    # allow_override=True permits a deliberate replacement.
    reg.register("foo", allow_override=True)(int)
    assert reg.get("foo") is int
    print("  -> Duplicate name raises unless allow_override=True [PASSED]")


def test_unknown_name_raises_with_helpful_message():
    print("\n[TEST 3] Testing an unknown plugin name raises a clear KeyError...")
    reg: PluginRegistry[type] = PluginRegistry(kind="widget")
    reg.register("foo")(object)
    with pytest.raises(KeyError) as exc_info:
        reg.get("bar")
    assert "widget" in str(exc_info.value)
    assert "foo" in str(exc_info.value)
    print(f"  -> KeyError message names the kind and lists registered names: {exc_info.value} [PASSED]")


@pytest.mark.parametrize(
    "protocol,expected_cls",
    [
        ("ros2", ROS2HardwareBridge),
        ("ros2_control", ROS2HardwareBridge),
        ("dds", ROS2HardwareBridge),
        ("sim", SimulationHardwareBridge),
        ("gazebo", SimulationHardwareBridge),
        ("isaac", SimulationHardwareBridge),
    ],
)
def test_connect_robot_dispatch_unchanged(protocol, expected_cls):
    print(f"\n[TEST] Testing connect_robot({protocol!r}) still dispatches to {expected_cls.__name__}...")
    spec = get_robot_spec("ur5e")
    bridge = UniversalRobotDriver.connect_robot(spec, protocol=protocol, uri="ros2://localhost")
    assert isinstance(bridge, expected_cls)
    bridge.disconnect()
    print(f"  -> {protocol!r} -> {expected_cls.__name__} [PASSED]")


def test_unknown_protocol_fails_closed():
    spec = get_robot_spec("ur5e")
    with pytest.raises(ValueError, match="Unknown robot protocol"):
        UniversalRobotDriver.connect_robot(
            spec, protocol="something_unrecognized", uri="ros2://localhost"
        )


if __name__ == "__main__":
    print("=== STARTING PLUGIN REGISTRY (PHASE 13) VERIFICATION ===")
    test_register_and_get()
    test_duplicate_registration_raises()
    test_unknown_name_raises_with_helpful_message()
    for protocol, expected_cls in [
        ("ros2", ROS2HardwareBridge), ("ros2_control", ROS2HardwareBridge),
        ("dds", ROS2HardwareBridge), ("sim", SimulationHardwareBridge),
        ("gazebo", SimulationHardwareBridge), ("isaac", SimulationHardwareBridge),
    ]:
        test_connect_robot_dispatch_unchanged(protocol, expected_cls)
    test_unknown_protocol_fails_closed()
    print("\n=== ALL PLUGIN REGISTRY TESTS PASSED SUCCESSFULLY ===")
