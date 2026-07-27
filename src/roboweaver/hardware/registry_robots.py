"""
Pre-configured Industrial & Collaborative Robot Hardware Profiles.
"""

from __future__ import annotations

import math
from roboweaver.hardware.robot_spec import JointSpec, LinkSpec, RobotSpec


def get_franka_panda_spec() -> RobotSpec:
    """Franka Emika Panda 7-DOF Collaborative Robot Arm."""
    return RobotSpec(
        id="franka_panda",
        name="Franka Emika Panda",
        manufacturer="Franka Robotics",
        dof=7,
        payload_capacity_kg=3.0,
        max_reach_m=0.855,
        base_height_m=0.140,
        joints=[
            JointSpec("panda_joint1", "revolute", (0, 0, 1), -2.8973, 2.8973, 2.1750, 87.0),
            JointSpec("panda_joint2", "revolute", (0, 1, 0), -1.7628, 1.7628, 2.1750, 87.0),
            JointSpec("panda_joint3", "revolute", (0, 0, 1), -2.8973, 2.8973, 2.1750, 87.0),
            JointSpec("panda_joint4", "revolute", (0, -1, 0), -3.0718, -0.0698, 2.1750, 87.0),
            JointSpec("panda_joint5", "revolute", (0, 0, 1), -2.8973, 2.8973, 2.6100, 12.0),
            JointSpec("panda_joint6", "revolute", (0, 1, 0), -0.0175, 3.7525, 2.6100, 12.0),
            JointSpec("panda_joint7", "revolute", (0, 0, 1), -2.8973, 2.8973, 2.6100, 12.0),
        ],
        links=[
            LinkSpec("panda_link1", 0.140, 4.97),
            LinkSpec("panda_link2", 0.192, 0.65),
            LinkSpec("panda_link3", 0.121, 3.22),
            LinkSpec("panda_link4", 0.207, 3.58),
            LinkSpec("panda_link5", 0.184, 1.23),
            LinkSpec("panda_link6", 0.088, 1.67),
            LinkSpec("panda_link7", 0.107, 0.73),
        ],
        description="7-DOF torque-controlled collaborative robot with high sensitivity",
    )


def get_ur5e_spec() -> RobotSpec:
    """Universal Robots UR5e 6-DOF Collaborative Robot Arm."""
    return RobotSpec(
        id="ur5e",
        name="Universal Robots UR5e",
        manufacturer="Universal Robots",
        dof=6,
        payload_capacity_kg=5.0,
        max_reach_m=0.850,
        base_height_m=0.162,
        joints=[
            JointSpec("shoulder_pan_joint", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 3.14, 150.0),
            JointSpec("shoulder_lift_joint", "revolute", (0, 1, 0), -math.pi * 2, math.pi * 2, 3.14, 150.0),
            JointSpec("elbow_joint", "revolute", (0, 1, 0), -math.pi, math.pi, 3.14, 150.0),
            JointSpec("wrist_1_joint", "revolute", (0, 1, 0), -math.pi * 2, math.pi * 2, 6.28, 28.0),
            JointSpec("wrist_2_joint", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 6.28, 28.0),
            JointSpec("wrist_3_joint", "revolute", (0, 1, 0), -math.pi * 2, math.pi * 2, 6.28, 28.0),
        ],
        links=[
            LinkSpec("shoulder_link", 0.162, 3.7),
            LinkSpec("upper_arm_link", 0.425, 8.3),
            LinkSpec("forearm_link", 0.392, 2.27),
            LinkSpec("wrist_1_link", 0.133, 1.2),
            LinkSpec("wrist_2_link", 0.099, 1.2),
            LinkSpec("wrist_3_link", 0.099, 0.2),
        ],
        description="Industry standard 6-DOF collaborative arm for assembly and pick-and-place",
    )


def get_kuka_iiwa_spec() -> RobotSpec:
    """KUKA LBR iiwa 14 R820 7-DOF Sensitive Arm."""
    return RobotSpec(
        id="kuka_iiwa",
        name="KUKA LBR iiwa 14 R820",
        manufacturer="KUKA Robotics",
        dof=7,
        payload_capacity_kg=14.0,
        max_reach_m=0.820,
        base_height_m=0.150,
        joints=[
            JointSpec("iiwa_joint_1", "revolute", (0, 0, 1), -2.96, 2.96, 1.48, 320.0),
            JointSpec("iiwa_joint_2", "revolute", (0, 1, 0), -2.09, 2.09, 1.48, 320.0),
            JointSpec("iiwa_joint_3", "revolute", (0, 0, 1), -2.96, 2.96, 1.74, 176.0),
            JointSpec("iiwa_joint_4", "revolute", (0, -1, 0), -2.09, 2.09, 1.30, 176.0),
            JointSpec("iiwa_joint_5", "revolute", (0, 0, 1), -2.96, 2.96, 2.26, 110.0),
            JointSpec("iiwa_joint_6", "revolute", (0, 1, 0), -2.09, 2.09, 2.35, 40.0),
            JointSpec("iiwa_joint_7", "revolute", (0, 0, 1), -3.05, 3.05, 2.35, 40.0),
        ],
        links=[
            LinkSpec("iiwa_link_1", 0.150, 5.0),
            LinkSpec("iiwa_link_2", 0.210, 5.0),
            LinkSpec("iiwa_link_3", 0.210, 4.0),
            LinkSpec("iiwa_link_4", 0.190, 3.5),
            LinkSpec("iiwa_link_5", 0.210, 3.5),
            LinkSpec("iiwa_link_6", 0.190, 2.5),
            LinkSpec("iiwa_link_7", 0.081, 1.2),
        ],
        description="High payload 7-DOF torque sensor integrated industrial arm",
    )


def get_kinova_gen3_spec() -> RobotSpec:
    """Kinova Gen3 7-DOF Lightweight Arm."""
    return RobotSpec(
        id="kinova_gen3",
        name="Kinova Gen3",
        manufacturer="Kinova Robotics",
        dof=7,
        payload_capacity_kg=4.0,
        max_reach_m=0.902,
        base_height_m=0.156,
        joints=[
            JointSpec("joint_1", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 1.74, 39.0),
            JointSpec("joint_2", "revolute", (0, 1, 0), -2.41, 2.41, 1.74, 39.0),
            JointSpec("joint_3", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 1.74, 39.0),
            JointSpec("joint_4", "revolute", (0, -1, 0), -2.66, 2.66, 1.74, 39.0),
            JointSpec("joint_5", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 2.26, 9.0),
            JointSpec("joint_6", "revolute", (0, 1, 0), -2.23, 2.23, 2.26, 9.0),
            JointSpec("joint_7", "revolute", (0, 0, 1), -math.pi * 2, math.pi * 2, 2.26, 9.0),
        ],
        links=[
            LinkSpec("link_1", 0.156, 1.37),
            LinkSpec("link_2", 0.210, 1.16),
            LinkSpec("link_3", 0.210, 1.16),
            LinkSpec("link_4", 0.208, 0.93),
            LinkSpec("link_5", 0.105, 0.68),
            LinkSpec("link_6", 0.105, 0.68),
            LinkSpec("link_7", 0.061, 0.40),
        ],
        description="Ultra-lightweight 7-DOF arm for research and mobile manipulation",
    )


def get_abb_irb120_spec() -> RobotSpec:
    """ABB IRB 120 6-DOF Compact Industrial Arm."""
    return RobotSpec(
        id="abb_irb120",
        name="ABB IRB 120",
        manufacturer="ABB Robotics",
        dof=6,
        payload_capacity_kg=3.0,
        max_reach_m=0.580,
        base_height_m=0.290,
        joints=[
            JointSpec("joint_1", "revolute", (0, 0, 1), -2.87, 2.87, 4.36, 100.0),
            JointSpec("joint_2", "revolute", (0, 1, 0), -1.91, 1.91, 4.36, 100.0),
            JointSpec("joint_3", "revolute", (0, 1, 0), -1.91, 1.22, 4.36, 100.0),
            JointSpec("joint_4", "revolute", (1, 0, 0), -2.79, 2.79, 5.58, 30.0),
            JointSpec("joint_5", "revolute", (0, 1, 0), -2.09, 2.09, 5.58, 30.0),
            JointSpec("joint_6", "revolute", (1, 0, 0), -6.98, 6.98, 7.33, 30.0),
        ],
        links=[
            LinkSpec("base_link", 0.290, 6.2),
            LinkSpec("link_1", 0.270, 4.0),
            LinkSpec("link_2", 0.270, 3.5),
            LinkSpec("link_3", 0.070, 2.0),
            LinkSpec("link_4", 0.302, 1.5),
            LinkSpec("link_5", 0.072, 0.5),
        ],
        description="High-speed compact 6-DOF industrial robot for electronics assembly",
    )


def get_temi_robot_spec() -> RobotSpec:
    """Temi Autonomous Mobile Service Robot (AMR with Display & Sensor Array)."""
    return RobotSpec(
        id="temi",
        name="Temi Service Robot",
        manufacturer="Temi Robotics",
        dof=3,
        payload_capacity_kg=10.0,
        max_reach_m=1.00,
        base_height_m=0.10,
        joints=[
            JointSpec("base_x", "prismatic", (1, 0, 0), -100.0, 100.0, 1.2, 50.0),
            JointSpec("base_y", "prismatic", (0, 1, 0), -100.0, 100.0, 1.2, 50.0),
            JointSpec("base_theta", "revolute", (0, 0, 1), -math.pi, math.pi, 2.5, 30.0),
        ],
        links=[
            LinkSpec("chassis_link", 0.30, 25.0),
            LinkSpec("torso_link", 0.70, 8.0),
            LinkSpec("screen_link", 0.20, 2.0),
        ],
        description="Autonomous mobile service robot with LiDAR SLAM, voice interface, and payload tray",
        has_force_torque_sensor=False,
    )


def get_pepper_robot_spec() -> RobotSpec:
    """SoftBank Pepper Humanoid Service Robot."""
    return RobotSpec(
        id="pepper",
        name="SoftBank Pepper Humanoid",
        manufacturer="SoftBank Robotics",
        dof=17,
        payload_capacity_kg=2.5,
        max_reach_m=0.60,
        base_height_m=0.12,
        joints=[
            # Base & Torso
            JointSpec("wheel_fl", "continuous", (0, 1, 0), -math.pi, math.pi, 2.0, 20.0),
            JointSpec("wheel_fr", "continuous", (0, 1, 0), -math.pi, math.pi, 2.0, 20.0),
            JointSpec("wheel_b", "continuous", (0, 1, 0), -math.pi, math.pi, 2.0, 20.0),
            JointSpec("hip_pitch", "revolute", (0, 1, 0), -0.5, 0.5, 1.0, 30.0),
            # Right Arm (6 DOF)
            JointSpec("r_shoulder_pitch", "revolute", (0, 1, 0), -2.08, 2.08, 2.0, 15.0),
            JointSpec("r_shoulder_roll", "revolute", (1, 0, 0), -1.56, 0.01, 2.0, 15.0),
            JointSpec("r_elbow_yaw", "revolute", (0, 0, 1), -2.08, 2.08, 2.0, 15.0),
            JointSpec("r_elbow_roll", "revolute", (1, 0, 0), 0.01, 1.56, 2.0, 15.0),
            JointSpec("r_wrist_yaw", "revolute", (0, 0, 1), -1.82, 1.82, 3.0, 5.0),
            JointSpec("r_hand", "revolute", (0, 0, 1), 0.0, 1.0, 3.0, 5.0),
            # Left Arm (6 DOF)
            JointSpec("l_shoulder_pitch", "revolute", (0, 1, 0), -2.08, 2.08, 2.0, 15.0),
            JointSpec("l_shoulder_roll", "revolute", (1, 0, 0), -0.01, 1.56, 2.0, 15.0),
            JointSpec("l_elbow_yaw", "revolute", (0, 0, 1), -2.08, 2.08, 2.0, 15.0),
            JointSpec("l_elbow_roll", "revolute", (1, 0, 0), -1.56, -0.01, 2.0, 15.0),
            JointSpec("l_wrist_yaw", "revolute", (0, 0, 1), -1.82, 1.82, 3.0, 5.0),
            JointSpec("l_hand", "revolute", (0, 0, 1), 0.0, 1.0, 3.0, 5.0),
            # Head
            JointSpec("head_yaw", "revolute", (0, 0, 1), -2.08, 2.08, 2.0, 5.0),
        ],
        links=[
            LinkSpec("base_link", 0.35, 18.0),
            LinkSpec("torso_link", 0.65, 8.0),
            LinkSpec("r_arm_link", 0.40, 2.2),
            LinkSpec("l_arm_link", 0.40, 2.2),
            LinkSpec("head_link", 0.25, 1.5),
        ],
        description="Humanoid mobile service robot with dual arms, social interaction display, and tactile sensors",
    )


def get_shadow_hand_spec() -> RobotSpec:
    """Shadow Dexterous Hand (20-DOF Multi-Finger Humanoid Hand)."""
    return RobotSpec(
        id="shadow_hand",
        name="Shadow Dexterous Hand",
        manufacturer="Shadow Robot Company",
        dof=20,
        payload_capacity_kg=4.0,
        max_reach_m=0.25,
        base_height_m=0.05,
        joints=[
            JointSpec(f"finger_joint_{i}", "revolute", (0, 0, 1), -0.35, 1.57, 4.0, 2.0)
            for i in range(20)
        ],
        links=[
            LinkSpec(f"finger_link_{i}", 0.04, 0.08)
            for i in range(20)
        ],
        description="20-DOF anthropomorphic dexterous robotic hand with tactile fingertips",
    )


def get_robotiq_hand_spec() -> RobotSpec:
    """Robotiq 3-Finger Adaptive Robot Gripper (4-DOF)."""
    return RobotSpec(
        id="robotiq_hand",
        name="Robotiq 3-Finger Adaptive Hand",
        manufacturer="Robotiq",
        dof=4,
        payload_capacity_kg=10.0,
        max_reach_m=0.20,
        base_height_m=0.08,
        joints=[
            JointSpec("finger_1_joint", "revolute", (0, 1, 0), 0.0, 1.22, 2.0, 5.0),
            JointSpec("finger_2_joint", "revolute", (0, 1, 0), 0.0, 1.22, 2.0, 5.0),
            JointSpec("finger_3_joint", "revolute", (0, 1, 0), 0.0, 1.22, 2.0, 5.0),
            JointSpec("palm_spread_joint", "revolute", (0, 0, 1), -0.28, 0.28, 1.0, 5.0),
        ],
        links=[
            LinkSpec("palm_link", 0.08, 0.9),
            LinkSpec("f1_link", 0.07, 0.2),
            LinkSpec("f2_link", 0.07, 0.2),
            LinkSpec("f3_link", 0.07, 0.2),
        ],
        description="4-DOF adaptive dexterous robot hand for versatile grasping of complex geometries",
    )


def get_inspire_hand_spec() -> RobotSpec:
    """Inspire Robots Dexterous Hand RH56F1-E2 (RS485 Serial Protocol)."""
    return RobotSpec(
        id="inspire_hand_rh56f1_e2",
        name="Inspire Hand RH56F1-E2",
        manufacturer="Inspire Robots",
        dof=6,
        payload_capacity_kg=5.0,
        max_reach_m=0.18,
        base_height_m=0.06,
        joints=[
            JointSpec("thumb_flex", "revolute", (0, 1, 0), 0.0, 1000.0, 50.0, 10.0),
            JointSpec("thumb_abduct", "revolute", (0, 0, 1), 0.0, 1000.0, 50.0, 10.0),
            JointSpec("index_flex", "revolute", (0, 1, 0), 0.0, 1000.0, 50.0, 10.0),
            JointSpec("middle_flex", "revolute", (0, 1, 0), 0.0, 1000.0, 50.0, 10.0),
            JointSpec("ring_flex", "revolute", (0, 1, 0), 0.0, 1000.0, 50.0, 10.0),
            JointSpec("pinky_flex", "revolute", (0, 1, 0), 0.0, 1000.0, 50.0, 10.0),
        ],
        links=[
            LinkSpec("palm_base_link", 0.15, 2.0),
            LinkSpec("thumb_link", 0.06, 0.5),
            LinkSpec("index_link", 0.08, 0.4),
            LinkSpec("middle_link", 0.08, 0.4),
            LinkSpec("ring_link", 0.07, 0.4),
            LinkSpec("pinky_link", 0.06, 0.3),
        ],
        description="6-DOF / 6-Actuator commercial anthropomorphic dexterous hand over RS485 (115200 baud)",
    )


def get_turtlebot4_spec() -> RobotSpec:
    """TurtleBot 4 Mobile Differential-Drive Robot with Card Scanner Payload (card_scannner_ws)."""
    return RobotSpec(
        id="turtlebot4",
        name="TurtleBot 4 Card Scanner",
        manufacturer="Clearpath / iRobot",
        dof=2,
        payload_capacity_kg=15.0,
        max_reach_m=25.0,  # Mobile navigation radius
        base_height_m=0.19,
        joints=[
            JointSpec("left_wheel_joint", "continuous", (0, 1, 0), -math.pi, math.pi, 10.0, 5.0),
            JointSpec("right_wheel_joint", "continuous", (0, 1, 0), -math.pi, math.pi, 10.0, 5.0),
            JointSpec("card_scanner_camera_joint", "fixed", (0, 0, 1), 0.0, 0.0, 0.0, 0.0),
        ],
        links=[
            LinkSpec("base_link", 0.35, 10.0),
            LinkSpec("wheel_left_link", 0.07, 0.5),
            LinkSpec("wheel_right_link", 0.07, 0.5),
            LinkSpec("card_scanner_payload_link", 0.10, 0.8),
        ],
        description="TurtleBot 4 mobile base equipped with vision/RFID card scanner payload for office/hospital logistics",
        has_force_torque_sensor=False,
    )


def get_generic_6dof_spec() -> RobotSpec:
    """Generic 6-DOF Robot Arm Profile."""
    return get_ur5e_spec()


ROBOT_REGISTRY: dict[str, RobotSpec] = {
    "franka_panda": get_franka_panda_spec(),
    "panda": get_franka_panda_spec(),
    "ur5e": get_ur5e_spec(),
    "ur10e": get_ur5e_spec(),
    "kuka_iiwa": get_kuka_iiwa_spec(),
    "kinova_gen3": get_kinova_gen3_spec(),
    "abb_irb120": get_abb_irb120_spec(),
    "temi": get_temi_robot_spec(),
    "pepper": get_pepper_robot_spec(),
    "shadow_hand": get_shadow_hand_spec(),
    "robotiq_hand": get_robotiq_hand_spec(),
    "inspire_hand_rh56f1_e2": get_inspire_hand_spec(),
    "inspire_hand": get_inspire_hand_spec(),
    "rh56f1": get_inspire_hand_spec(),
    "rh56f1_e2": get_inspire_hand_spec(),
    "turtlebot4": get_turtlebot4_spec(),
    "turtlebot3": get_turtlebot4_spec(),
    "turtlebot": get_turtlebot4_spec(),
    "card_scanner": get_turtlebot4_spec(),
    "generic_6dof": get_generic_6dof_spec(),
}


def get_robot_spec(robot_id: str) -> RobotSpec:
    """Retrieve RobotSpec by robot_id (defaults to Franka Panda)."""
    key = robot_id.lower().strip()
    return ROBOT_REGISTRY.get(key, get_franka_panda_spec())


