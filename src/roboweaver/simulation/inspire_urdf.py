"""
URDF Generator for Inspire Robots RH56F1-E2 Anthropomorphic Dexterous Hand.

Generates a complete, standard ROS 2 / PyBullet / Gazebo compatible URDF file
modeling the 6 independent actuators, palm chassis, and finger linkages.
"""

from __future__ import annotations
from pathlib import Path


def generate_inspire_urdf(output_path: str | Path | None = None) -> str:
    """Generate valid URDF XML for the Inspire RH56F1-E2 Dexterous Hand."""
    urdf_xml = """<?xml version="1.0" encoding="utf-8"?>
<!-- Inspire Robots RH56F1-E2 Anthropomorphic 6-DOF Dexterous Hand URDF -->
<robot name="inspire_hand_rh56f1_e2">

  <!-- Materials -->
  <material name="dark_gray">
    <color rgba="0.2 0.2 0.2 1.0"/>
  </material>
  <material name="metallic_blue">
    <color rgba="0.1 0.4 0.8 1.0"/>
  </material>
  <material name="tactile_black">
    <color rgba="0.05 0.05 0.05 1.0"/>
  </material>

  <!-- Palm Base Link -->
  <link name="palm_base_link">
    <inertial>
      <mass value="0.45"/>
      <origin xyz="0 0 0.03" rpy="0 0 0"/>
      <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.001"/>
    </inertial>
    <visual>
      <origin xyz="0 0 0.03" rpy="0 0 0"/>
      <geometry>
        <box size="0.08 0.03 0.10"/>
      </geometry>
      <material name="dark_gray"/>
    </visual>
    <collision>
      <origin xyz="0 0 0.03" rpy="0 0 0"/>
      <geometry>
        <box size="0.08 0.03 0.10"/>
      </geometry>
    </collision>
  </link>

  <!-- Thumb Abduction (Revolute Joint 0) -->
  <link name="thumb_base_link">
    <inertial>
      <mass value="0.03"/>
      <origin xyz="-0.03 0 0.02" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="-0.03 0 0.02" rpy="0 0 0"/>
      <geometry>
        <cylinder radius="0.012" length="0.03"/>
      </geometry>
      <material name="metallic_blue"/>
    </visual>
  </link>
  <joint name="thumb_abduct" type="revolute">
    <parent link="palm_base_link"/>
    <child link="thumb_base_link"/>
    <origin xyz="-0.035 0 0.02" rpy="0 0 0"/>
    <axis xyz="0 0 1"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

  <!-- Thumb Flexion (Revolute Joint 1) -->
  <link name="thumb_link">
    <inertial>
      <mass value="0.02"/>
      <origin xyz="-0.02 0 0.02" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="-0.02 0 0.02" rpy="0 -0.3 0"/>
      <geometry>
        <box size="0.015 0.015 0.05"/>
      </geometry>
      <material name="tactile_black"/>
    </visual>
  </link>
  <joint name="thumb_flex" type="revolute">
    <parent link="thumb_base_link"/>
    <child link="thumb_link"/>
    <origin xyz="-0.01 0 0.02" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

  <!-- Index Finger Flexion (Revolute Joint 2) -->
  <link name="index_link">
    <inertial>
      <mass value="0.02"/>
      <origin xyz="-0.02 0 0.04" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="-0.02 0 0.04" rpy="0 0 0"/>
      <geometry>
        <box size="0.014 0.014 0.08"/>
      </geometry>
      <material name="tactile_black"/>
    </visual>
  </link>
  <joint name="index_flex" type="revolute">
    <parent link="palm_base_link"/>
    <child link="index_link"/>
    <origin xyz="-0.028 0 0.08" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

  <!-- Middle Finger Flexion (Revolute Joint 3) -->
  <link name="middle_link">
    <inertial>
      <mass value="0.02"/>
      <origin xyz="0 0 0.045" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="0 0 0.045" rpy="0 0 0"/>
      <geometry>
        <box size="0.014 0.014 0.085"/>
      </geometry>
      <material name="tactile_black"/>
    </visual>
  </link>
  <joint name="middle_flex" type="revolute">
    <parent link="palm_base_link"/>
    <child link="middle_link"/>
    <origin xyz="-0.009 0 0.082" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

  <!-- Ring Finger Flexion (Revolute Joint 4) -->
  <link name="ring_link">
    <inertial>
      <mass value="0.02"/>
      <origin xyz="0.02 0 0.04" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="0.02 0 0.04" rpy="0 0 0"/>
      <geometry>
        <box size="0.014 0.014 0.075"/>
      </geometry>
      <material name="tactile_black"/>
    </visual>
  </link>
  <joint name="ring_flex" type="revolute">
    <parent link="palm_base_link"/>
    <child link="ring_link"/>
    <origin xyz="0.010 0 0.08" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

  <!-- Pinky Finger Flexion (Revolute Joint 5) -->
  <link name="pinky_link">
    <inertial>
      <mass value="0.02"/>
      <origin xyz="0.03 0 0.035" rpy="0 0 0"/>
      <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
    </inertial>
    <visual>
      <origin xyz="0.03 0 0.035" rpy="0 0 0"/>
      <geometry>
        <box size="0.012 0.012 0.065"/>
      </geometry>
      <material name="tactile_black"/>
    </visual>
  </link>
  <joint name="pinky_flex" type="revolute">
    <parent link="palm_base_link"/>
    <child link="pinky_link"/>
    <origin xyz="0.028 0 0.075" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="0.0" upper="1.57" effort="10.0" velocity="2.0"/>
  </joint>

</robot>
"""
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(urdf_xml.strip(), encoding="utf-8")
    return urdf_xml.strip()
