"""
Universal Robotics Package & Knowledge Nexus (RoboticsPackageNexus).

Indexes, queries, and recommends ROS/ROS 2 packages, sensor drivers, middleware,
navigation stacks, manipulation frameworks, and custom workspaces across the entire
robotics ecosystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class PackageSpec:
    """Specification of a ROS / ROS 2 package, library, or middleware component."""
    id: str
    name: str
    category: str  # "navigation", "manipulation", "perception", "control", "fleet", "middleware"
    description: str
    compatible_robots: list[str]
    ros2_dependencies: list[str]
    default_topics: list[str]
    default_actions: list[str]
    version: str = "2.0.0"


class RoboticsPackageNexus:
    """Universal Robotics Package Nexus — Built-in Knowledge Base for all robotic packages."""

    PACKAGE_CATALOG: dict[str, PackageSpec] = {
        # === NAVIGATION & MOBILE ===
        "nav2_bringup": PackageSpec(
            id="nav2_bringup",
            name="ROS 2 Navigation Stack (Nav2)",
            category="navigation",
            description="Production-grade autonomous navigation, dynamic obstacle avoidance, and behavior trees for mobile robots",
            compatible_robots=["turtlebot4", "temi", "pepper", "generic_6dof"],
            ros2_dependencies=["nav2_msgs", "nav2_behavior_tree", "rclcpp_action"],
            default_topics=["/cmd_vel", "/odom", "/map", "/scan"],
            default_actions=["/navigate_to_pose", "/navigate_through_poses"],
        ),
        "slam_toolbox": PackageSpec(
            id="slam_toolbox",
            name="SLAM Toolbox",
            category="navigation",
            description="2D/3D SLAM, lifelong map localization, and graph-based mapping for laser-equipped mobile robots",
            compatible_robots=["turtlebot4", "temi", "pepper"],
            ros2_dependencies=["sensor_msgs", "nav_msgs"],
            default_topics=["/scan", "/map", "/tf"],
            default_actions=["/slam_toolbox/save_map"],
        ),
        "card_scanner_ws": PackageSpec(
            id="card_scanner_ws",
            name="Visitor ID & Security Card Scanner Workspace",
            category="perception",
            description="RFID & optical card scanning payload stack for mobile receptionist robots and visitor authentication",
            compatible_robots=["turtlebot4", "temi"],
            ros2_dependencies=["sensor_msgs", "cv_bridge", "vision_msgs"],
            default_topics=["/card_scanner/image_raw", "/card_scanner/badge_id", "/card_scanner/status"],
            default_actions=["/scan_visitor_badge"],
        ),
        # === MANIPULATION & GRASPING ===
        "moveit2": PackageSpec(
            id="moveit2",
            name="MoveIt 2 Motion Planning Framework",
            category="manipulation",
            description="State-of-the-art motion planning, collision checking, IK solving, and trajectory optimization for robotic arms",
            compatible_robots=["franka_panda", "ur5e", "ur10e", "kuka_iiwa", "kinova_gen3", "abb_irb120"],
            ros2_dependencies=["moveit_core", "moveit_ros_planning_interface", "moveit_msgs"],
            default_topics=["/joint_states", "/display_planned_path", "/planning_scene"],
            default_actions=["/move_action"],
        ),
        "inspire_hand_ros2": PackageSpec(
            id="inspire_hand_ros2",
            name="Inspire RH56F1-E2 Dexterous Hand Driver",
            category="manipulation",
            description="6-DOF / 6-Actuator RS485 serial driver and gesture action server for Inspire anthropomorphic dexterous hand",
            compatible_robots=["inspire_hand_rh56f1_e2"],
            ros2_dependencies=["ros2_control", "controller_manager", "sensor_msgs"],
            default_topics=["/inspire_hand/joint_states", "/inspire_hand/actuator_forces"],
            default_actions=["/inspire_hand/set_gesture", "/inspire_hand/grasp_object"],
        ),
        "shadow_hand_ros2": PackageSpec(
            id="shadow_hand_ros2",
            name="Shadow Dexterous Hand 20-DOF Control Stack",
            category="manipulation",
            description="20-DOF tendon-driven tactile hand controller and bio-IK interface",
            compatible_robots=["shadow_hand"],
            ros2_dependencies=["ros2_control", "sensor_msgs", "trajectory_msgs"],
            default_topics=["/shadow_hand/joint_states", "/shadow_hand/tactile"],
            default_actions=["/shadow_hand/execute_trajectory"],
        ),
        # === PERCEPTION & VISION ===
        "apriltag_ros": PackageSpec(
            id="apriltag_ros",
            name="AprilTag ROS 2 Node",
            category="perception",
            description="Fiducial marker detection, 3D pose estimation, and visual docking",
            compatible_robots=["turtlebot4", "temi", "pepper", "franka_panda", "ur5e"],
            ros2_dependencies=["sensor_msgs", "geometry_msgs", "image_transport"],
            default_topics=["/tag_detections", "/camera/image_raw"],
            default_actions=[],
        ),
        "realsense2_camera": PackageSpec(
            id="realsense2_camera",
            name="Intel RealSense ROS 2 Driver",
            category="perception",
            description="RGB-D pointcloud stream, depth imaging, and IMU interface for D435i/D455 cameras",
            compatible_robots=["franka_panda", "ur5e", "turtlebot4", "temi"],
            ros2_dependencies=["sensor_msgs", "stereo_msgs", "cv_bridge"],
            default_topics=["/camera/color/image_raw", "/camera/depth/color/points"],
            default_actions=[],
        ),
        # === HARDWARE & CONTROL ===
        "ros2_control": PackageSpec(
            id="ros2_control",
            name="ROS 2 Control & Hardware Interface Architecture",
            category="control",
            description="Real-time hardware resource manager, joint trajectory controllers, and sensor broadcasting",
            compatible_robots=["franka_panda", "ur5e", "kuka_iiwa", "kinova_gen3", "abb_irb120", "inspire_hand_rh56f1_e2", "shadow_hand"],
            ros2_dependencies=["controller_manager", "hardware_interface", "pluginlib"],
            default_topics=["/joint_states", "/dynamic_joint_states"],
            default_actions=["/follow_joint_trajectory"],
        ),
        # === MULTI-ROBOT / FLEET & ORCHESTRATION ===
        "behaviortree_cpp_v3": PackageSpec(
            id="behaviortree_cpp_v3",
            name="BehaviorTree.CPP Execution Engine",
            category="fleet",
            description="Reactive, hierarchical execution trees for single-robot and multi-robot choreography",
            compatible_robots=["franka_panda", "ur5e", "temi", "pepper", "turtlebot4", "inspire_hand_rh56f1_e2"],
            ros2_dependencies=["rclcpp", "ament_index_cpp"],
            default_topics=["/behavior_tree_log", "/groot_monitoring"],
            default_actions=[],
        ),
        "shopmate_r_fleet": PackageSpec(
            id="shopmate_r_fleet",
            name="ShopMate-R Multi-Robot Retail Workcell",
            category="fleet",
            description="Coordinated retail automation connecting Temi (navigation), Pepper (interaction), and Franka Panda (restocking)",
            compatible_robots=["temi", "pepper", "franka_panda"],
            ros2_dependencies=["nav2_bringup", "moveit2", "behaviortree_cpp_v3"],
            default_topics=["/temi/cmd_vel", "/pepper/speech", "/franka_panda/joint_states"],
            default_actions=["/shopmate_r/execute_workcell"],
        ),
    }

    @classmethod
    def get_package(cls, package_id: str) -> PackageSpec | None:
        """Retrieve package specification by ID."""
        return cls.PACKAGE_CATALOG.get(package_id.lower().strip())

    @classmethod
    def get_all_packages(cls) -> list[PackageSpec]:
        """Return all cataloged robotics packages."""
        return list(cls.PACKAGE_CATALOG.values())

    @classmethod
    def query_by_category(cls, category: str) -> list[PackageSpec]:
        """Filter packages by category (e.g. navigation, manipulation, perception, fleet)."""
        cat = category.lower().strip()
        return [p for p in cls.PACKAGE_CATALOG.values() if p.category == cat]

    @classmethod
    def query_by_robot(cls, robot_id: str) -> list[PackageSpec]:
        """Find all packages compatible with a given robot."""
        rid = robot_id.lower().strip()
        return [
            p for p in cls.PACKAGE_CATALOG.values()
            if rid in p.compatible_robots or "generic_6dof" in p.compatible_robots
        ]

    @classmethod
    def query_by_keyword(cls, keyword: str) -> list[PackageSpec]:
        """Search packages by natural language keyword."""
        kw = keyword.lower().strip()
        results = []
        for p in cls.PACKAGE_CATALOG.values():
            if (
                kw in p.id.lower()
                or kw in p.name.lower()
                or kw in p.description.lower()
                or kw in p.category.lower()
            ):
                results.append(p)
        return results

    @classmethod
    def recommend_stack_for_prompt(cls, prompt: str) -> dict[str, Any]:
        """Recommend the optimal ROS 2 package stack, topics, and actions for a natural language task prompt."""
        lower = prompt.lower()
        recommended_pkg_ids: list[str] = ["ros2_control", "behaviortree_cpp_v3"]
        matched_robots: list[str] = []

        # Check for card scanning / TurtleBot
        if any(w in lower for w in ["card", "scan", "rfid", "badge", "visitor", "turtlebot"]):
            recommended_pkg_ids.extend(["nav2_bringup", "slam_toolbox", "card_scanner_ws", "apriltag_ros"])
            matched_robots.append("turtlebot4")

        # Check for ShopMate-R / retail
        if "shopmate" in lower or "retail" in lower:
            recommended_pkg_ids.extend(["shopmate_r_fleet", "nav2_bringup", "moveit2"])
            matched_robots.extend(["temi", "pepper", "franka_panda"])

        # Check for manipulation / grasping / arm
        if any(w in lower for w in ["pick", "place", "restock", "arm", "franka", "ur5", "grasp", "bolt"]):
            if "moveit2" not in recommended_pkg_ids:
                recommended_pkg_ids.append("moveit2")

        # Check for Inspire hand
        if any(w in lower for w in ["inspire", "rh56f1", "finger", "dexterous", "hand"]):
            recommended_pkg_ids.append("inspire_hand_ros2")
            if "inspire_hand_rh56f1_e2" not in matched_robots:
                matched_robots.append("inspire_hand_rh56f1_e2")

        # Deduplicate
        seen = set()
        unique_ids = []
        for pid in recommended_pkg_ids:
            if pid not in seen and pid in cls.PACKAGE_CATALOG:
                seen.add(pid)
                unique_ids.append(pid)

        pkgs = [cls.PACKAGE_CATALOG[pid] for pid in unique_ids]
        all_topics = sorted(list({t for p in pkgs for t in p.default_topics}))
        all_actions = sorted(list({a for p in pkgs for a in p.default_actions}))
        all_deps = sorted(list({d for p in pkgs for d in p.ros2_dependencies}))

        return {
            "recommended_packages": [p.name for p in pkgs],
            "package_ids": unique_ids,
            "matched_robots": matched_robots or ["franka_panda"],
            "ros2_topics": all_topics,
            "ros2_actions": all_actions,
            "package_xml_dependencies": all_deps,
        }
