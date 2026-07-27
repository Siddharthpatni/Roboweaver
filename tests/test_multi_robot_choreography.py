"""
Comprehensive Verification Suite for Universal Multi-Robot Workcell Choreography.

Verifies:
1. Heterogeneous Robot Hardware Profiles (Temi AMR, Pepper Humanoid, Shadow Dexterous Hand, Robotiq Hand)
2. Multi-Robot DAG Scheduling & Choreography Pipeline
3. Composite BehaviorTree XML with Parallel and Sequence execution tiers
4. Multi-Robot ROS 2 Launch Package Generation with multi-namespace action servers and DDS QoS
"""

import shutil
from pathlib import Path
from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import UniversalRobotDriver
from roboweaver.fleet import MultiRobotChoreographer


def test_heterogeneous_service_and_dexterous_robots():
    """Verify profiles for Temi, Pepper, Shadow Hand, and Robotiq Hand, and honest bridge status.

    rclpy isn't pip-installable, so without a real ROS 2 distro the bridge must honestly report
    is_connected=False rather than fake a live DDS link — see ROS2HardwareBridge.connect().
    """
    print("[TEST 1] Testing Heterogeneous Robot Profiles (Temi, Pepper, Dexterous Hands)...")

    try:
        import rclpy  # noqa: F401
        rclpy_available = True
    except ImportError:
        rclpy_available = False

    new_robots = [
        ("temi", 3, "Temi Service Robot"),
        ("pepper", 17, "SoftBank Pepper Humanoid"),
        ("shadow_hand", 20, "Shadow Dexterous Hand"),
        ("robotiq_hand", 4, "Robotiq 3-Finger Adaptive Hand"),
    ]
    for r_id, expected_dof, expected_name in new_robots:
        spec = get_robot_spec(r_id)
        assert spec.dof == expected_dof
        assert spec.name == expected_name
        bridge = UniversalRobotDriver.connect_robot(spec, protocol="ros2", uri="ros2://localhost")
        status = bridge.connect()
        assert status.is_connected == rclpy_available
        assert status.dof == expected_dof
        bridge.disconnect()
        label = "LIVE" if status.is_connected else "NOT CONNECTED (rclpy unavailable, honest fallback)"
        print(f"  -> Verified [{spec.name:30s}] ({spec.dof}-DOF) bridge status: {label} via {status.protocol} [PASSED]")


def test_multi_robot_choreography_pipeline():
    """Verify building and compiling a multi-robot choreography across Temi, Pepper, Shadow Hand, and Franka."""
    print("\n[TEST 2] Testing Multi-Robot Choreography Pipeline (Hospital Logistics Workcell)...")

    choreographer = MultiRobotChoreographer(workcell_name="Hospital_Logistics")

    # Step 1: Temi navigates to pharmacy
    choreographer.add_robot_task(
        step_id="step_1_temi_nav",
        robot_id="temi",
        instruction="Navigate to pharmacy storage shelf",
    )

    # Step 2: Temi transports payload to hallway handover
    choreographer.add_robot_task(
        step_id="step_2_temi_transport",
        robot_id="temi",
        instruction="Pick up vial tray and transport to hallway handover station",
        depends_on=["step_1_temi_nav"],
    )

    # Step 3: Pepper receives tray from Temi
    choreographer.add_robot_task(
        step_id="step_3_pepper_handover",
        robot_id="pepper",
        instruction="Receive vial tray from Temi and greet medical staff",
        depends_on=["step_2_temi_transport"],
        handover_target="pepper",
    )

    # Step 4: Pepper places tray on inspection workbench
    choreographer.add_robot_task(
        step_id="step_4_pepper_bench",
        robot_id="pepper",
        instruction="Transfer vial tray to inspection workbench",
        depends_on=["step_3_pepper_handover"],
    )

    # Step 5: Shadow Dexterous Hand grasps vial (Parallel Tier with Step 6)
    choreographer.add_robot_task(
        step_id="step_5_shadow_hand_grasp",
        robot_id="shadow_hand",
        instruction="Grasp medical vial with 20-DOF tactile fingertips",
        depends_on=["step_4_pepper_bench"],
    )

    # Step 6: Franka Panda arm inspects surface under microscope (Parallel Tier with Step 5)
    choreographer.add_robot_task(
        step_id="step_6_franka_inspect",
        robot_id="franka_panda",
        instruction="Inspect surface of vial under microscope",
        depends_on=["step_4_pepper_bench"],
    )

    # 1. Test compilation
    schedule = choreographer.compile_workcell(verbose=False)
    assert len(schedule.steps) == 6
    for step in schedule.steps.values():
        assert step.compiled_skill is not None
    print("  -> Compiled all 6 choreographed tasks across Temi, Pepper, Shadow Hand, and Franka [PASSED]")

    # 2. Test execution tiers (topological sorting & parallel stages)
    tiers = schedule.get_execution_tiers()
    assert len(tiers) == 5  # Step 1 -> Step 2 -> Step 3 -> Step 4 -> [Step 5, Step 6 in parallel]
    assert len(tiers[4]) == 2
    print(f"  -> Successfully computed 5 execution tiers (Tier 5 contains 2 parallel tasks: {tiers[4][0].robot_id} & {tiers[4][1].robot_id}) [PASSED]")

    # 3. Test Composite BehaviorTree XML Generation
    bt_xml = choreographer.generate_composite_behavior_tree()
    assert '<BehaviorTree ID="Workcell_Hospital_Logistics_Root">' in bt_xml
    assert '<Parallel ID="Parallel_Tier_4">' in bt_xml
    assert 'ID="[shadow_hand] step_5_shadow_hand_grasp: Grasp medical vial with 20-DOF tactile fingertips"' in bt_xml
    assert 'ID="[franka_panda] step_6_franka_inspect: Inspect surface of vial under microscope"' in bt_xml
    print("  -> Generated composite Groot2 BehaviorTree XML with synchronized <Parallel> & <Sequence> nodes [PASSED]")

    # 4. Test Multi-Robot ROS 2 Launch Package Export
    out_dir = Path("/Users/siddharthpatni/.gemini/antigravity-ide/scratch/roboweaver/test_output_tmp_choreography")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        pkg_path = choreographer.export_workcell_ros2_package(out_dir)
        assert pkg_path.exists()
        assert (pkg_path / "composite_workcell_bt.xml").exists()
        assert (pkg_path / "package.xml").exists()
        assert (pkg_path / "setup.py").exists()
        assert (pkg_path / "robot_agent_node.py").exists()
        assert (pkg_path / "config" / "inter_robot_dds.yaml").exists()
        assert (pkg_path / "launch" / "workcell_orchestration.launch.py").exists()

        launch_txt = (pkg_path / "launch" / "workcell_orchestration.launch.py").read_text(encoding="utf-8")
        assert "namespace='/temi'" in launch_txt
        assert "namespace='/pepper'" in launch_txt
        assert "namespace='/shadow_hand'" in launch_txt
        assert "namespace='/franka_panda'" in launch_txt

        print(f"  -> Generated Multi-Robot ROS 2 Launch Package: [{pkg_path.name}]")
        print("  -> Verified multi-namespace launch script (/temi, /pepper, /shadow_hand, /franka_panda) [PASSED]")
        print("  -> Verified config/inter_robot_dds.yaml & composite_workcell_bt.xml [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=== STARTING ROBOWEAVER MULTI-ROBOT CHOREOGRAPHY VERIFICATION ===")
    test_heterogeneous_service_and_dexterous_robots()
    test_multi_robot_choreography_pipeline()
    print("\n=== ALL MULTI-ROBOT CHOREOGRAPHY VERIFICATION TESTS PASSED SUCCESSFULLY ===")
