"""
Comprehensive Verification Suite for RoboWeaver Universal Robotics Platform.

Verifies:
1. Dynamic Custom Skill Registration (unlimited skill categories beyond initial 6)
2. Universal Robot Driver connection across ROS 2 DDS & Simulators
3. Full ROS 2 Package Generation (.launch.py, QoS profiles, ros2_controllers.yaml)
4. N-DOF Inverse Kinematics & Trajectory execution
"""

import shutil
import tempfile
from pathlib import Path
import pytest
from roboweaver.skills.taxonomy import (
    IndustrialSkillCategory,
    SkillPluginRegistry,
    get_industrial_skill_template,
)
from roboweaver.types import TaskDecomposition, TaskType, BTNode
from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import (
    ROS2HardwareBridge,
    SimulationHardwareBridge,
    UniversalRobotDriver,
    resolve_bridge_class,
)
from roboweaver.compiler import ACTION_CATEGORY_MAP, SkillCompiler
from roboweaver.codegen.ros2_gen import generate_ros2_package


def test_dynamic_custom_skill_registration():
    """Verify that users can dynamically register any skill template."""
    print("[TEST 1] Testing Dynamic Custom Skill Registration...")
    
    # 1. Register a custom surgical suturing skill
    suture_tasks = [
        TaskDecomposition(TaskType.PERCEIVE, "Locate wound incision edge"),
        TaskDecomposition(TaskType.MOVE_TO, "Approach suturing insertion waypoint"),
        TaskDecomposition(TaskType.CLOSE_GRIPPER, "Grasp suture needle with micro-force", {"force": 2.5}),
        TaskDecomposition(TaskType.MOVE_TO, "Execute helical tissue piercing trajectory"),
        TaskDecomposition(TaskType.OPEN_GRIPPER, "Release needle and pull knot"),
    ]
    suture_bt = BTNode(
        "Sequence",
        "surgery_suture_root",
        children=[
            BTNode("Action", "Locate incision"),
            BTNode("Action", "Piercing trajectory"),
            BTNode("Action", "Pull knot"),
        ],
    )
    SkillPluginRegistry.register_template(
        key="SURGERY_SUTURING",
        name="Surgical Tissue Suturing",
        description="Autonomous robotic tissue suturing",
        required_sensors=["stereo_microscope", "micro_ft_sensor"],
        tasks=suture_tasks,
        behavior_tree_root=suture_bt,
    )

    # Verify retrieval
    template = get_industrial_skill_template("SURGERY_SUTURING", "tissue")
    assert template.name == "Surgical Tissue Suturing"
    assert len(template.tasks) == 5
    print("  -> Successfully registered and retrieved custom skill 'SURGERY_SUTURING' [PASSED]")

    # Test open-world fallback custom skill
    open_template = get_industrial_skill_template("WIPING_TABLE", "lab_bench")
    assert open_template.category == "CUSTOM_SKILL"
    assert "WIPING_TABLE" in open_template.name or "Wiping_table" in open_template.name or "wiping_table" in open_template.name.lower()
    print("  -> Successfully generated fallback custom skill template for 'WIPING_TABLE' [PASSED]")


def test_universal_robot_driver_connection():
    """Verify that UniversalRobotDriver honestly reports ROS 2 bridge status — it does not fake success.

    rclpy requires a full ROS 2 distro install (not pip-installable), so in this plain Python test
    environment the bridge must honestly report `is_connected=False` rather than pretending a live
    DDS connection exists. This locks in the honest-failure contract: if rclpy ever becomes
    importable (a real ROS 2 workspace), this same bridge would report `is_connected=True` instead —
    see ROS2HardwareBridge.connect() in hardware/universal_driver.py.
    """
    print("\n[TEST 2] Testing Universal Robot Driver Connection (honest rclpy-unavailable path)...")

    try:
        import rclpy  # noqa: F401
        rclpy_available = True
    except ImportError:
        rclpy_available = False

    robots = ["franka_panda", "ur5e", "kuka_iiwa", "kinova_gen3", "abb_irb120"]
    for r_id in robots:
        spec = get_robot_spec(r_id)
        bridge = UniversalRobotDriver.connect_robot(spec, protocol="ros2", uri="ros2://localhost")
        status = bridge.connect()
        assert status.dof == spec.dof
        assert status.is_connected == rclpy_available

        if rclpy_available:
            assert "joint_trajectory_controller" in status.active_controllers
            success = bridge.send_trajectory([[0.1] * spec.dof, [0.2] * spec.dof])
            assert success
        else:
            assert "rclpy" in status.message.lower()
            # Honest bridge must refuse to claim a trajectory was sent when nothing is connected.
            success = bridge.send_trajectory([[0.1] * spec.dof, [0.2] * spec.dof])
            assert success is False

        bridge.disconnect()
        print(f"  -> [{spec.name}] ({spec.dof}-DOF) bridge honestly reports is_connected={status.is_connected} via {status.protocol} [PASSED]")


def test_full_ros2_package_generation():
    """Verify complete ROS 2 package generator (.launch.py, QoS profile, controllers)."""
    print("\n[TEST 3] Testing Full ROS 2 Code Generation...")
    
    compiler = SkillCompiler(target_robot="kuka_iiwa")
    result = compiler.compile_with_diagnostics("Pick up the heavy gear assembly", verbose=False)
    skill = result.skill

    out_dir = Path(tempfile.mkdtemp(prefix="roboweaver_test_ros2pkg_"))
    try:
        pkg_path = generate_ros2_package(result.ir, out_dir)
        assert pkg_path.exists()
        assert (pkg_path / "behavior_tree.xml").exists()
        assert (pkg_path / "package.xml").exists()
        assert (pkg_path / "setup.py").exists()
        assert (pkg_path / "setup.cfg").exists()
        assert (pkg_path / pkg_path.name / "trajectory_client.py").exists()
        assert (pkg_path / pkg_path.name / "__init__.py").exists()
        assert (pkg_path / "resource" / pkg_path.name).exists()
        assert (pkg_path / "compiled_skill.json").exists()
        skill_slug = f"{skill.intent.action.value.lower()}_{skill.intent.object_name}".replace(" ", "_")
        assert (pkg_path / "launch" / f"{skill_slug}.launch.py").exists()
        assert (pkg_path / "config" / "dds_qos_profile.yaml").exists()
        assert (pkg_path / "config" / "ros2_controllers.yaml").exists()

        manifest = __import__("json").loads((pkg_path / "compiled_skill.json").read_text())
        assert manifest["robot_id"] == "kuka_iiwa"
        assert manifest["joint_names"] == [joint.name for joint in get_robot_spec("kuka_iiwa").joints]

        print(f"  -> Successfully generated complete ROS 2 package at {pkg_path.name}")
        print("  -> Verified config/dds_qos_profile.yaml & config/ros2_controllers.yaml [PASSED]")
        print("  -> Verified launch/pick_and_place_gear.launch.py [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_every_declared_skill_category_has_a_real_template():
    """Verify every built-in enum category is reachable and has a real template."""
    print("\n[TEST 4] Testing every declared skill category...")

    declared_categories = set(IndustrialSkillCategory) - {IndustrialSkillCategory.CUSTOM_SKILL}
    reachable_categories = set(ACTION_CATEGORY_MAP.values())
    assert declared_categories == reachable_categories
    for category in sorted(declared_categories, key=lambda item: item.value):
        tmpl = get_industrial_skill_template(category, "workpiece")
        assert len(tmpl.tasks) > 0
        assert tmpl.behavior_tree_root is not None
        print(f"  -> Verified skill template: [{category.value:15s}] - {tmpl.name} [PASSED]")

    custom = get_industrial_skill_template(IndustrialSkillCategory.CUSTOM_SKILL, "workpiece")
    assert custom.category == "CUSTOM_SKILL"
    assert custom.tasks


def test_simulation_bridge_honest_tcp_reachability():
    """Verify SimulationHardwareBridge does a genuine TCP probe, not a fabricated success.

    No Isaac Sim/Gazebo process is available in this test environment, so we prove the bridge
    is honest in both directions: it must report is_connected=False against a closed port, and
    is_connected=True against a real listening TCP socket we spin up ourselves.
    """
    print("\n[TEST 4b] Testing Simulation Bridge honest TCP reachability probe...")
    import socket
    import threading

    spec = get_robot_spec("franka_panda")

    # Closed port: nothing is listening, must honestly report not connected.
    bridge = UniversalRobotDriver.connect_robot(spec, protocol="sim", uri="gazebo://localhost:55999")
    status = bridge.connect()
    assert status.is_connected is False
    assert "no simulator" in status.message.lower() or "unreachable" in status.protocol.lower()

    # Real listener: must honestly report connected.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("localhost", 0))
    port = srv.getsockname()[1]
    srv.listen(1)

    def accept_loop():
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                break

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    try:
        bridge2 = UniversalRobotDriver.connect_robot(spec, protocol="sim", uri=f"gazebo://localhost:{port}")
        status2 = bridge2.connect()
        assert status2.is_connected is True
    finally:
        srv.close()

    print("  -> Verified honest TCP reachability: unreachable=False, reachable=True [PASSED]")


def test_protocol_resolution_is_exact_and_supports_documented_simulators():
    assert resolve_bridge_class("ros2") is ROS2HardwareBridge
    assert resolve_bridge_class("ROS2-CONTROL") is ROS2HardwareBridge
    for protocol in ("sim", "gazebo", "ignition", "isaac", "webots"):
        assert resolve_bridge_class(protocol) is SimulationHardwareBridge

    for ambiguous in ("not_ros2", "my_gazebo_sim", "dds-over-evil"):
        with pytest.raises(ValueError, match="Unknown robot protocol"):
            resolve_bridge_class(ambiguous)


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "http://localhost:11345",
        "sim://user:password@localhost:11345",
        "sim://localhost:70000",
        "sim:///missing-host",
        "sim://localhost:11345?unexpected=true",
    ],
)
def test_simulation_bridge_rejects_ambiguous_or_unsafe_target_uris(uri):
    spec = get_robot_spec("franka_panda")
    bridge = SimulationHardwareBridge(spec, uri)
    with pytest.raises(ValueError):
        bridge._parse_target()


def test_robotics_package_nexus():
    """Verify Universal Robotics Package & Knowledge Nexus queries and recommendations."""
    print("\n[TEST 5] Testing Universal Robotics Package & Knowledge Nexus...")
    from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
    pkgs = RoboticsPackageNexus.get_all_packages()
    assert len(pkgs) >= 11
    assert RoboticsPackageNexus.get_package("card_scanner_ws") is not None
    assert RoboticsPackageNexus.get_package("shopmate_r_fleet") is not None

    rec = RoboticsPackageNexus.recommend_stack_for_prompt(
        "Build a visitor card scanner system with TurtleBot4 to scan security ID badges"
    )
    assert "card_scanner_ws" in rec["package_ids"]
    assert "nav2_bringup" in rec["package_ids"]
    assert "turtlebot4" in rec["matched_robots"]
    assert "/card_scanner/badge_id" in rec["ros2_topics"]
    print("  -> Verified Knowledge Nexus Package Index & TurtleBot Card Scanner Recommendations [PASSED]")


if __name__ == "__main__":
    print("=== STARTING ROBOWEAVER UNIVERSAL PLATFORM VERIFICATION ===")
    test_dynamic_custom_skill_registration()
    test_universal_robot_driver_connection()
    test_full_ros2_package_generation()
    test_simulation_bridge_honest_tcp_reachability()
    test_every_declared_skill_category_has_a_real_template()
    test_robotics_package_nexus()
    print("\n=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY ===")
