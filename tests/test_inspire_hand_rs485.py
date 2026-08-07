"""
Verification Suite for Inspire Robots Dexterous Hand RH56F1-E2 (RS485).

Verifies:
1. Hardware Specification registration (6-DOF actuator control)
2. RS485 Modbus RTU driver & loopback simulation
3. Dexterous grasping gesture library (open, fist, pinch, precision_grip, cylindrical_grip)
4. ROS 2 Package & Action Server generation (roboweaver_inspire_hand_rh56f1)
5. Prompt-to-System Multi-Robot integration
"""

import shutil
import tempfile
from pathlib import Path
import pytest
from roboweaver.hardware import get_robot_spec, InspireHandRS485Driver
from roboweaver.hardware.inspire_hand_rs485 import InspireHandCommError
from roboweaver.codegen.inspire_ros2_gen import generate_inspire_hand_ros2_package
from roboweaver.fleet import PromptToWorkcellBuilder, SystemPromptParser


def test_inspire_hand_hardware_spec():
    """Verify Inspire RH56F1-E2 RobotSpec definition in hardware registry."""
    print("[TEST 1] Testing Inspire RH56F1-E2 (RS485) Hardware Specification...")
    spec = get_robot_spec("inspire_hand_rh56f1_e2")
    assert spec.dof == 6
    assert spec.manufacturer == "Inspire Robots"
    assert len(spec.joints) == 6
    assert spec.joints[0].name == "thumb_flex"
    assert spec.joints[5].name == "pinky_flex"
    print(f"  -> Verified Specification: [{spec.name}] ({spec.dof}-DOF) [PASSED]")


def test_inspire_hand_rs485_driver_and_gestures():
    """Verify RS485 Driver packet framing, actuator position control, and gesture library."""
    print("\n[TEST 2] Testing Inspire RH56F1-E2 RS485 Driver & Gesture Library...")
    driver = InspireHandRS485Driver(
        port="/definitely/not/a/serial/device",
        baudrate=115200,
        allow_simulation=True,
    )
    state = driver.connect()
    assert state.is_connected is False
    assert driver.simulated  # Simulation is explicit and never presented as hardware connectivity.

    # 1. Test manual 6-actuator position control
    driver.set_positions([500, 300, 700, 700, 0, 0])
    state = driver.read_state()
    assert state.actuator_positions == [500, 300, 700, 700, 0, 0]
    assert state.actuator_forces_n[0] > 0.0  # Force simulation active
    print("  -> Verified 6-Actuator Position & Grasping Force simulation [PASSED]")

    # 2. Test Dexterous Gesture Library
    for gesture in ["fist", "pinch", "precision_grip", "cylindrical_grip", "open"]:
        success = driver.set_gesture(gesture)
        assert success
        assert driver.state.gesture_active == gesture
    print("  -> Verified Dexterous Gesture Library (fist, pinch, precision_grip, cylindrical_grip, open) [PASSED]")
    driver.disconnect()


def test_inspire_hand_connection_failure_is_fail_closed():
    driver = InspireHandRS485Driver(port="/definitely/not/a/serial/device")
    state = driver.connect()

    assert state.is_connected is False
    assert driver.simulated is False
    assert driver.last_connect_error
    with pytest.raises(InspireHandCommError, match="not connected"):
        driver.set_gesture("open")


def test_inspire_hand_ros2_package_generation():
    """Verify generating complete ROS 2 package for Inspire RH56F1-E2."""
    print("\n[TEST 3] Testing Inspire RH56F1-E2 ROS 2 Package Generation...")
    out_dir = Path(tempfile.mkdtemp(prefix="roboweaver_test_inspire_ros2ws_"))
    try:
        pkg = generate_inspire_hand_ros2_package(
            output_dir=out_dir,
            serial_port="/dev/ttyUSB0",
            baudrate=115200,
        )
        assert pkg.exists()
        assert (pkg / "package.xml").exists()
        assert (pkg / "setup.py").exists()
        assert (pkg / "inspire_hand_action_server.py").exists()
        assert (pkg / "config" / "inspire_rh56f1_controllers.yaml").exists()
        assert (pkg / "launch" / "inspire_hand_rs485.launch.py").exists()

        ctrl_yaml = (pkg / "config" / "inspire_rh56f1_controllers.yaml").read_text(encoding="utf-8")
        assert "thumb_flex" in ctrl_yaml
        assert "pinky_flex" in ctrl_yaml
        assert "JointGroupPositionController" in ctrl_yaml

        print(f"  -> Successfully generated ROS 2 package: [{pkg.name}] [PASSED]")
        print("  -> Verified ros2_control YAML (/config/inspire_rh56f1_controllers.yaml) [PASSED]")
        print("  -> Verified RS485 action server (/inspire_hand_action_server.py) [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_inspire_hand_prompt_builder():
    """Verify Prompt-to-System Multi-Robot integration with Inspire RH56F1-E2."""
    print("\n[TEST 4] Testing Prompt-to-System Integration for Inspire RH56F1-E2...")
    prompt = "Build medical inspection cell with Franka Panda arm and Inspire RH56F1-E2 dexterous hand"
    parsed = SystemPromptParser.parse(prompt)
    assert "inspire_hand_rh56f1_e2" in parsed.robots
    assert "franka_panda" in parsed.robots

    out_dir = Path(tempfile.mkdtemp(prefix="roboweaver_test_inspire_workcell_"))
    try:
        choreographer, pkg_path = PromptToWorkcellBuilder.build_from_prompt(
            prompt, output_dir=out_dir, verbose=False
        )
        assert pkg_path is not None
        assert (pkg_path / "launch" / "workcell_orchestration.launch.py").exists()
        launch_txt = (pkg_path / "launch" / "workcell_orchestration.launch.py").read_text(encoding="utf-8")
        assert "namespace='/inspire_hand_rh56f1_e2'" in launch_txt
        print("  -> Verified Prompt-to-Workcell Multi-Robot Package with Inspire Hand [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=== STARTING ROBOWEAVER INSPIRE RH56F1-E2 (RS485) VERIFICATION ===")
    test_inspire_hand_hardware_spec()
    test_inspire_hand_rs485_driver_and_gestures()
    test_inspire_hand_ros2_package_generation()
    test_inspire_hand_prompt_builder()
    print("\n=== ALL INSPIRE RH56F1-E2 VERIFICATION TESTS PASSED SUCCESSFULLY ===")
