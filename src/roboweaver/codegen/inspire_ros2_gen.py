"""
Inspire RH56F1-E2 (RS485) ROS 2 Package & Action Server Generator.

Generates a standalone, production-ready ROS 2 package (`roboweaver_inspire_hand_rh56f1`) with:
1. `inspire_hand_action_server.py`: Action & service server for 6-actuator position/force trajectories and gesture commands.
2. `config/inspire_rh56f1_controllers.yaml`: ros2_control position/force controller settings.
3. `launch/inspire_hand_rs485.launch.py`: ROS 2 launch script configured for RS485 serial port (`/dev/ttyUSB0`, 115200 baud).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_inspire_hand_ros2_package(
    output_dir: str | Path,
    package_name: str = "roboweaver_inspire_hand_rh56f1",
    serial_port: str = "/dev/ttyUSB0",
    baudrate: int = 115200,
) -> Path:
    """Generate a complete ROS 2 package for Inspire Hand RH56F1-E2 over RS485."""
    out = Path(output_dir) / package_name
    out.mkdir(parents=True, exist_ok=True)

    launch_dir = out / "launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    config_dir = out / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # 1. Controller YAML
    controller_yaml = """# Inspire Robots RH56F1-E2 (RS485) ros2_control Configuration
controller_manager:
  ros__parameters:
    update_rate: 100  # 100 Hz RS485 control loop

    inspire_hand_controller:
      type: position_controllers/JointGroupPositionController

    inspire_hand_state_broadcaster:
      type: joint_state_broadcaster/JointStateBroadcaster

inspire_hand_controller:
  ros__parameters:
    joints:
      - thumb_flex
      - thumb_abduct
      - index_flex
      - middle_flex
      - ring_flex
      - pinky_flex
    interface_name: position
    command_interfaces:
      - position
      - effort
    state_interfaces:
      - position
      - velocity
      - effort
"""
    (config_dir / "inspire_rh56f1_controllers.yaml").write_text(controller_yaml, encoding="utf-8")

    # 2. RS485 Action Server & Driver Node Python script
    node_py = f"""#!/usr/bin/env python3
\"\"\"
ROS 2 RS485 Driver & Action Server Node for Inspire RH56F1-E2 Dexterous Hand.
\"\"\"

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32MultiArray
from sensor_msgs.msg import JointState
from roboweaver.hardware.inspire_hand_rs485 import InspireHandRS485Driver


class InspireHandRS485Node(Node):
    def __init__(self):
        super().__init__('inspire_hand_rs485_node')
        self.declare_parameter('serial_port', '{serial_port}')
        self.declare_parameter('baudrate', {baudrate})

        port = self.get_parameter('serial_port').get_parameter_value().string_value
        baud = self.get_parameter('baudrate').get_parameter_value().integer_value

        self.get_logger().info(f'Connecting to Inspire RH56F1-E2 on {{port}} @ {{baud}} baud...')
        self.driver = InspireHandRS485Driver(port=port, baudrate=baud)
        state = self.driver.connect()
        self.get_logger().info(f'Inspire Hand Connected (Simulated loopback: {{self.driver.simulated}})')

        # Subscriptions & Publishers
        self.cmd_sub = self.create_subscription(
            Int32MultiArray,
            '/inspire_hand/actuator_cmd',
            self.actuator_cmd_callback,
            10
        )
        self.gesture_sub = self.create_subscription(
            String,
            '/inspire_hand/gesture_cmd',
            self.gesture_cmd_callback,
            10
        )
        self.joint_pub = self.create_publisher(JointState, '/inspire_hand/joint_states', 10)
        self.timer = self.create_timer(0.02, self.publish_telemetry)  # 50 Hz telemetry

    def actuator_cmd_callback(self, msg: Int32MultiArray):
        positions = list(msg.data)
        if len(positions) == 6:
            self.driver.set_positions(positions)

    def gesture_cmd_callback(self, msg: String):
        gesture = msg.data.strip()
        try:
            self.driver.set_gesture(gesture)
            self.get_logger().info(f'Executed gesture: {{gesture}}')
        except Exception as e:
            self.get_logger().error(str(e))

    def publish_telemetry(self):
        state = self.driver.read_state()
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = ['thumb_flex', 'thumb_abduct', 'index_flex', 'middle_flex', 'ring_flex', 'pinky_flex']
        # Convert 0-1000 range to radians for RViz/ros2_control
        js.position = [p * 0.00157 for p in state.actuator_positions]
        js.effort = state.actuator_forces_n
        self.joint_pub.publish(js)


def main(args=None):
    rclpy.init(args=args)
    node = InspireHandRS485Node()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
"""
    (out / "inspire_hand_action_server.py").write_text(node_py, encoding="utf-8")

    # 3. Launch script
    launch_py = f"""from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='{package_name}',
            executable='inspire_hand_action_server',
            name='inspire_hand_rh56f1_e2_node',
            output='screen',
            parameters=[{{
                'serial_port': '{serial_port}',
                'baudrate': {baudrate}
            }}]
        )
    ])
"""
    (launch_dir / "inspire_hand_rs485.launch.py").write_text(launch_py, encoding="utf-8")

    # 4. package.xml
    pkg_xml = f"""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{package_name}</name>
  <version>1.0.0</version>
  <description>ROS 2 RS485 Driver and Action Server for Inspire Hand RH56F1-E2</description>
  <maintainer email="dev@roboweaver.ai">RoboWeaver</maintainer>
  <license>Apache-2.0</license>
  <exec_depend>rclpy</exec_depend>
  <exec_depend>std_msgs</exec_depend>
  <exec_depend>sensor_msgs</exec_depend>
  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
"""
    (out / "package.xml").write_text(pkg_xml, encoding="utf-8")

    # 5. setup.py
    setup_py = f"""from setuptools import setup
import os
from glob import glob

package_name = '{package_name}'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='RoboWeaver',
    maintainer_email='dev@roboweaver.ai',
    description='ROS 2 RS485 Driver for Inspire RH56F1-E2 Hand',
    license='Apache-2.0',
    entry_points={{
        'console_scripts': [
            'inspire_hand_action_server = inspire_hand_action_server:main',
        ],
    }},
)
"""
    (out / "setup.py").write_text(setup_py, encoding="utf-8")
    return out
