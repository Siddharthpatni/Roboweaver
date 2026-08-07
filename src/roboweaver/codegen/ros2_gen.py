"""Deterministic ROS 2 package generation from a compiled robot skill.

The generated package is a valid ``ament_python`` package.  It contains the
selected robot's real joint names and the optimized waypoints produced by the
compiler; no placeholder trajectory is introduced during lowering.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from roboweaver.codegen.groot2 import export_groot2_ir
from roboweaver.identifiers import safe_identifier
from roboweaver.ir.schema import RoboIR

if TYPE_CHECKING:
    from roboweaver.codegen.ai_codegen import AICodeReviewer
    from roboweaver.hardware.robot_spec import RobotSpec


def _resolve_robot_spec(ir: RoboIR, robot_spec: "RobotSpec | None") -> "RobotSpec":
    if robot_spec is None:
        from roboweaver.hardware.registry_robots import get_robot_spec

        robot_spec = get_robot_spec(ir.execution.robot_id)

    problems = robot_spec.validate()
    if problems:
        raise ValueError(
            f"Cannot generate ROS 2 package for invalid RobotSpec '{robot_spec.id}': "
            + "; ".join(problems)
        )
    if robot_spec.id != ir.execution.robot_id:
        raise ValueError(
            "ROS 2 target does not match the compiled motion plan: "
            f"IR targets '{ir.execution.robot_id}', requested '{robot_spec.id}'. "
            "Retarget and re-run safety verification before code generation."
        )
    return robot_spec


def _compiled_trajectories(ir: RoboIR, dof: int) -> list[dict[str, Any]]:
    if ir.lowering is None:
        raise ValueError("RoboIR has no concrete lowering; ROS 2 generation is impossible.")
    trajectories: list[dict[str, Any]] = []
    for segment in ir.lowering.trajectories:
        name = segment.task_description
        if not segment.waypoints:
            raise ValueError(f"Trajectory segment '{name}' has no waypoints.")
        duration = float(segment.duration_s)
        if not math.isfinite(duration) or duration < 0.0:
            raise ValueError(f"Trajectory segment '{name}' has invalid duration {duration!r}.")

        waypoints: list[list[float]] = []
        for index, waypoint in enumerate(segment.waypoints):
            if len(waypoint) != dof:
                raise ValueError(
                    f"Trajectory segment '{name}' waypoint {index} has {len(waypoint)} "
                    f"positions; target robot requires {dof}."
                )
            values = [float(value) for value in waypoint]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(
                    f"Trajectory segment '{name}' waypoint {index} contains a non-finite value."
                )
            waypoints.append(values)

        trajectories.append({"name": name, "duration": duration, "waypoints": waypoints})

    if not trajectories:
        raise ValueError("Compiled skill contains no trajectories to lower to ROS 2.")
    return trajectories


def _render_action_client(
    *,
    package_name: str,
    skill_slug: str,
    robot_id: str,
    joint_names: list[str],
    trajectories: list[dict[str, Any]],
) -> str:
    joint_names_json = json.dumps(joint_names, ensure_ascii=True)
    trajectories_json = json.dumps(trajectories, ensure_ascii=True, separators=(",", ":"))
    return f'''#!/usr/bin/env python3
"""Generated RoboWeaver trajectory client for {skill_slug} on {robot_id}."""

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectoryPoint


JOINT_NAMES = {joint_names_json}
COMPILED_TRAJECTORIES = {trajectories_json}
TOTAL_WAYPOINTS = sum(len(segment["waypoints"]) for segment in COMPILED_TRAJECTORIES)
CONTROLLER_ACTION = "/joint_trajectory_controller/follow_joint_trajectory"


class RoboWeaverSkillNode(Node):
    """Submit the compiler-produced trajectory and verify controller completion."""

    def __init__(self):
        super().__init__("{package_name}_node")
        self._client = ActionClient(self, FollowJointTrajectory, CONTROLLER_ACTION)

    def _goal(self):
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(JOINT_NAMES)
        elapsed = 0.0

        for segment in COMPILED_TRAJECTORIES:
            waypoints = segment["waypoints"]
            # Keep timestamps strictly increasing, including zero-duration
            # compiler segments, because controllers reject duplicate times.
            step_duration = max(float(segment["duration"]) / len(waypoints), 1e-6)
            for positions in waypoints:
                elapsed += step_duration
                point = JointTrajectoryPoint()
                point.positions = list(positions)
                point.time_from_start = Duration(seconds=elapsed).to_msg()
                goal.trajectory.points.append(point)

        return goal

    def execute_skill(self, server_timeout_s=10.0):
        if not self._client.wait_for_server(timeout_sec=server_timeout_s):
            self.get_logger().error(
                f"Trajectory controller unavailable at {{CONTROLLER_ACTION}}"
            )
            return False

        goal_future = self._client.send_goal_async(self._goal())
        rclpy.spin_until_future_complete(self, goal_future)
        goal_handle = goal_future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().error("Trajectory controller rejected the compiled skill")
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        wrapped_result = result_future.result()
        if wrapped_result is None:
            self.get_logger().error("Trajectory controller returned no result")
            return False

        result = wrapped_result.result
        if result.error_code != FollowJointTrajectory.Result.SUCCESSFUL:
            self.get_logger().error(
                f"Trajectory failed with code {{result.error_code}}: {{result.error_string}}"
            )
            return False

        self.get_logger().info(
            f"Compiled skill completed: {{TOTAL_WAYPOINTS}} waypoints"
        )
        return True


def main(args=None):
    rclpy.init(args=args)
    node = RoboWeaverSkillNode()
    try:
        succeeded = node.execute_skill()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    if not succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
'''


def generate_ros2_package(
    ir: RoboIR,
    output_dir: str | Path,
    ai_review: bool = False,
    reviewer: "AICodeReviewer | None" = None,
    robot_spec: "RobotSpec | None" = None,
) -> Path:
    """Lower complete ``ir`` into a robot-specific, installable ROS 2 package.

    ``robot_spec`` is optional for compatibility with direct callers. When it is
    omitted the exact target stored on the IR execution spec is resolved from
    the registry. A mismatched explicit target is rejected because changing
    embodiment after planning would bypass IK and safety verification.

    AI review is sidecar-only: deterministic executable source is never replaced.
    """
    if ir.program is None or ir.lowering is None:
        raise ValueError("ROS 2 code generation requires complete RoboIR program and lowering data.")
    robot_spec = _resolve_robot_spec(ir, robot_spec)
    joint_names = list(ir.lowering.joint_names)
    expected_joint_names = [joint.name for joint in robot_spec.joints[: robot_spec.dof]]
    if joint_names != expected_joint_names:
        raise ValueError("RoboIR lowering joint names do not match the selected RobotSpec.")
    trajectories = _compiled_trajectories(ir, robot_spec.dof)

    out = Path(output_dir)
    skill_slug = safe_identifier(
        f"{ir.action}_{ir.program.object_name}", default="skill"
    )
    package_name = f"roboweaver_{skill_slug}"
    pkg_dir = out / package_name
    launch_dir = pkg_dir / "launch"
    config_dir = pkg_dir / "config"
    resource_dir = pkg_dir / "resource"
    python_dir = pkg_dir / package_name
    for directory in (launch_dir, config_dir, resource_dir, python_dir):
        directory.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "behavior_tree.xml").write_text(export_groot2_ir(ir), encoding="utf-8")
    (resource_dir / package_name).write_text("", encoding="utf-8")
    (python_dir / "__init__.py").write_text("", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "skill": skill_slug,
        "robot_id": robot_spec.id,
        "robot_name": robot_spec.name,
        "joint_names": joint_names,
        "trajectories": trajectories,
        "roboir": ir.to_dict(),
    }
    (pkg_dir / "compiled_skill.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    qos_yaml = """# QoS policy for command/status communication.
qos_profile:
  reliability: RMW_QOS_POLICY_RELIABILITY_RELIABLE
  durability: RMW_QOS_POLICY_DURABILITY_VOLATILE
  deadline: 100  # ms
  liveliness: RMW_QOS_POLICY_LIVELINESS_AUTOMATIC
"""
    (config_dir / "dds_qos_profile.yaml").write_text(qos_yaml, encoding="utf-8")

    joint_yaml = "\n".join(f"      - {name}" for name in joint_names)
    ros2_control_yaml = f"""# Robot-specific controller configuration for {robot_spec.id}
controller_manager:
  ros__parameters:
    update_rate: 100
    joint_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster
    joint_trajectory_controller:
      type: joint_trajectory_controller/JointTrajectoryController

joint_trajectory_controller:
  ros__parameters:
    joints:
{joint_yaml}
    command_interfaces:
      - position
    state_interfaces:
      - position
      - velocity
    allow_partial_joints_goal: false
    state_publish_rate: 100.0
"""
    (config_dir / "ros2_controllers.yaml").write_text(
        ros2_control_yaml, encoding="utf-8"
    )

    py_code = _render_action_client(
        package_name=package_name,
        skill_slug=skill_slug,
        robot_id=robot_spec.id,
        joint_names=joint_names,
        trajectories=trajectories,
    )
    trajectory_client_path = python_dir / "trajectory_client.py"
    trajectory_client_path.write_text(py_code, encoding="utf-8")

    if ai_review:
        if reviewer is None:
            from roboweaver.codegen.ai_codegen import AICodeReviewer

            reviewer = AICodeReviewer()
        review = reviewer.review_ros2(
            py_code,
            robot_id=robot_spec.id,
            action=ir.action,
            object_name=ir.program.object_name,
            dof=robot_spec.dof,
        )
        if review.annotated_code:
            (pkg_dir / "trajectory_client.ai_review.py").write_text(
                review.annotated_code.rstrip() + "\n", encoding="utf-8"
            )
        (pkg_dir / "ai_review.json").write_text(
            json.dumps(
                {
                    "model": review.model,
                    "latency_s": review.latency_s,
                    "issues": review.issues,
                    "suggestions": review.suggestions,
                    "error": review.error,
                    "annotated_file": (
                        "trajectory_client.ai_review.py" if review.annotated_code else None
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    launch_py = f'''from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="{package_name}",
            executable="trajectory_client",
            name="{package_name}_node",
            output="screen",
        )
    ])
'''
    (launch_dir / f"{skill_slug}.launch.py").write_text(launch_py, encoding="utf-8")

    package_xml = f'''<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{package_name}</name>
  <version>1.0.0</version>
  <description>Robot-specific RoboWeaver trajectory package for {skill_slug} on {robot_spec.id}</description>
  <maintainer email="dev@roboweaver.ai">RoboWeaver Platform</maintainer>
  <license>Apache-2.0</license>
  <buildtool_depend>ament_python</buildtool_depend>
  <exec_depend>rclpy</exec_depend>
  <exec_depend>control_msgs</exec_depend>
  <exec_depend>trajectory_msgs</exec_depend>
  <exec_depend>ros2_controllers</exec_depend>
  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
'''
    (pkg_dir / "package.xml").write_text(package_xml, encoding="utf-8")

    setup_py = f'''from glob import glob
import os
from setuptools import setup

package_name = "{package_name}"

setup(
    name=package_name,
    version="1.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "behavior_tree.xml", "compiled_skill.json"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RoboWeaver",
    maintainer_email="dev@roboweaver.ai",
    description="Robot-specific trajectory package generated by RoboWeaver",
    license="Apache-2.0",
    entry_points={{
        "console_scripts": [
            "trajectory_client = {package_name}.trajectory_client:main",
        ],
    }},
)
'''
    (pkg_dir / "setup.py").write_text(setup_py, encoding="utf-8")
    (pkg_dir / "setup.cfg").write_text(
        f"[develop]\nscript_dir=$base/lib/{package_name}\n"
        f"[install]\ninstall_scripts=$base/lib/{package_name}\n",
        encoding="utf-8",
    )

    return pkg_dir
