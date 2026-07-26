"""
Universal Multi-Robot Workcell & Choreography Pipeline.

Orchestrates heterogeneous robot fleets working together on composite tasks:
- Service & Mobile Robots (Temi, SoftBank Pepper, AMRs)
- Industrial & Cobot Arms (Franka Panda, UR5e, KUKA, Kinova, ABB)
- Dexterous Multi-Finger Hands (Shadow Hand, Robotiq 3-Finger Gripper)

Features:
1. DAG Task Scheduling across multiple robots with dependency tracking
2. Inter-Robot Handover & DDS Sync Token orchestration
3. Multi-Robot ROS 2 Launch and Composite BehaviorTree XML Generation
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec, RobotSpec
from roboweaver.types import CompiledSkill, BTNode
from roboweaver.codegen.groot2 import export_groot2_xml


@dataclass
class WorkcellTaskStep:
    """A single atomic step assigned to a specific robot in a multi-robot choreography."""
    step_id: str
    robot_id: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)
    handover_target: str | None = None
    compiled_skill: CompiledSkill | None = None


@dataclass
class WorkcellSchedule:
    """Directed Acyclic Graph (DAG) schedule of multi-robot tasks."""
    workcell_name: str
    steps: dict[str, WorkcellTaskStep] = field(default_factory=dict)

    def add_step(
        self,
        step_id: str,
        robot_id: str,
        instruction: str,
        depends_on: list[str] | None = None,
        handover_target: str | None = None,
    ) -> WorkcellTaskStep:
        step = WorkcellTaskStep(
            step_id=step_id,
            robot_id=robot_id,
            instruction=instruction,
            depends_on=depends_on or [],
            handover_target=handover_target,
        )
        self.steps[step_id] = step
        return step

    def get_execution_tiers(self) -> list[list[WorkcellTaskStep]]:
        """Topologically sort steps into parallel execution tiers."""
        remaining = dict(self.steps)
        completed = set()
        tiers = []

        while remaining:
            current_tier = []
            for s_id, step in list(remaining.items()):
                if all(dep in completed for dep in step.depends_on):
                    current_tier.append(step)
            if not current_tier:
                raise ValueError("Cyclic dependency detected in multi-robot WorkcellSchedule!")
            for step in current_tier:
                completed.add(step.step_id)
                del remaining[step.step_id]
            tiers.append(current_tier)
        return tiers


class MultiRobotChoreographer:
    """Universal Choreographer pipeline for building complete multi-robot systems."""

    def __init__(self, workcell_name: str = "Universal_Workcell"):
        self.workcell_name = workcell_name
        self.schedule = WorkcellSchedule(workcell_name=workcell_name)
        self.compilers: dict[str, SkillCompiler] = {}

    def _get_compiler(self, robot_id: str) -> SkillCompiler:
        key = robot_id.lower().strip()
        if key not in self.compilers:
            self.compilers[key] = SkillCompiler(target_robot=key)
        return self.compilers[key]

    def add_robot_task(
        self,
        step_id: str,
        robot_id: str,
        instruction: str,
        depends_on: list[str] | None = None,
        handover_target: str | None = None,
    ) -> WorkcellTaskStep:
        """Add a choreographed task step for a specific robot."""
        return self.schedule.add_step(
            step_id=step_id,
            robot_id=robot_id,
            instruction=instruction,
            depends_on=depends_on,
            handover_target=handover_target,
        )

    def compile_workcell(self, verbose: bool = True) -> WorkcellSchedule:
        """Compile all task steps for each target robot embodiment."""
        if verbose:
            print(f"\n\033[1;35m━━━ Multi-Robot Choreography Pipeline: [{self.workcell_name}] ━━━\033[0m")
            print(f"  Total Choreographed Steps: {len(self.schedule.steps)}")

        for s_id, step in self.schedule.steps.items():
            compiler = self._get_compiler(step.robot_id)
            if verbose:
                print(f"\n  [Compiling Step: {step.step_id}] -> Robot: \033[36m{step.robot_id}\033[0m")
            step.compiled_skill = compiler.compile(step.instruction, verbose=False)
            if verbose:
                spec = compiler.robot_spec
                print(f"    ✓ Compiled for {spec.name} ({spec.dof}-DOF) | Intent: {step.compiled_skill.intent.action.value}")

        return self.schedule

    def generate_composite_behavior_tree(self) -> str:
        """Generate a unified Groot2 BehaviorTree XML orchestrating all robots across parallel and sequential tiers."""
        tiers = self.schedule.get_execution_tiers()
        tier_nodes = []

        for tier_idx, tier in enumerate(tiers):
            if len(tier) == 1:
                step = tier[0]
                node = BTNode("Action", f"[{step.robot_id}] {step.step_id}: {step.instruction}")
            else:
                parallel_children = [
                    BTNode("Action", f"[{step.robot_id}] {step.step_id}: {step.instruction}")
                    for step in tier
                ]
                node = BTNode("Parallel", f"Parallel_Tier_{tier_idx}", children=parallel_children)
            tier_nodes.append(node)

        root = BTNode("Sequence", f"Workcell_{self.workcell_name}_Root", children=tier_nodes)
        
        # Convert root BTNode to XML string
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<root BTCPP_format="4">',
            f'  <BehaviorTree ID="{root.name}">',
        ]
        self._format_bt_node_xml(root, xml_lines, depth=4)
        xml_lines.append('  </BehaviorTree>')
        xml_lines.append('</root>')
        return "\n".join(xml_lines)

    def _format_bt_node_xml(self, node: BTNode, lines: list[str], depth: int):
        indent = " " * depth
        if not node.children:
            lines.append(f'{indent}<{node.type} ID="{node.name}" />')
        else:
            lines.append(f'{indent}<{node.type} ID="{node.name}">')
            for c in node.children:
                self._format_bt_node_xml(c, lines, depth + 2)
            lines.append(f'{indent}</{node.type}>')

    def export_workcell_ros2_package(self, output_dir: str | Path) -> Path:
        """Generate a complete multi-robot ROS 2 launch and orchestration package."""
        out = Path(output_dir)
        pkg_slug = f"roboweaver_workcell_{self.workcell_name.lower().replace(' ', '_')}"
        pkg_dir = out / pkg_slug
        pkg_dir.mkdir(parents=True, exist_ok=True)
        launch_dir = pkg_dir / "launch"
        launch_dir.mkdir(parents=True, exist_ok=True)
        config_dir = pkg_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save composite BehaviorTree XML
        bt_xml = self.generate_composite_behavior_tree()
        (pkg_dir / "composite_workcell_bt.xml").write_text(bt_xml, encoding="utf-8")

        # 2. Save inter-robot DDS sync configuration
        dds_yaml = """# Universal Multi-Robot Workcell Inter-Robot DDS Communication & QoS
workcell_dds:
  sync_topic: "/workcell/sync_token"
  handover_topic: "/workcell/handover_state"
  qos_policy:
    reliability: "RELIABLE"
    durability: "TRANSIENT_LOCAL"
    deadline_ms: 50
"""
        (config_dir / "inter_robot_dds.yaml").write_text(dds_yaml, encoding="utf-8")

        # 3. Generate multi-namespace ROS 2 launch script (.launch.py)
        launch_nodes_py = []
        unique_robots = set(step.robot_id for step in self.schedule.steps.values())
        for r_id in sorted(unique_robots):
            launch_nodes_py.append(f"""        Node(
            package='roboweaver_workcell_{self.workcell_name.lower()}',
            executable='robot_agent_node',
            name='{r_id}_orchestrator_node',
            namespace='/{r_id}',
            output='screen',
            parameters=[{{
                'robot_id': '{r_id}',
                'dds_config': 'inter_robot_dds.yaml'
            }}]
        ),""")

        launch_py = f"""from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    \"\"\"Universal Multi-Robot Workcell Launch Description for {self.workcell_name}.\"\"\"
    return LaunchDescription([
{chr(10).join(launch_nodes_py)}
    ])
"""
        (launch_dir / "workcell_orchestration.launch.py").write_text(launch_py, encoding="utf-8")

        # 4. Generate universal robot agent runner Python script
        agent_py = f"""#!/usr/bin/env python3
\"\"\"Universal ROS 2 Multi-Robot Choreography Agent Node.\"\"\"

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class WorkcellRobotAgent(Node):
    def __init__(self):
        super().__init__('workcell_robot_agent')
        self.declare_parameter('robot_id', 'generic_robot')
        robot_id = self.get_parameter('robot_id').get_parameter_value().string_value
        self.get_logger().info(f'RoboWeaver Multi-Robot Agent Active for [namespace: {{robot_id}}]')


def main(args=None):
    rclpy.init(args=args)
    node = WorkcellRobotAgent()
    rclpy.spin_once(node, timeout_sec=1.0)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
"""
        (pkg_dir / "robot_agent_node.py").write_text(agent_py, encoding="utf-8")

        # 5. Save package.xml
        pkg_xml = f"""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{pkg_slug}</name>
  <version>1.0.0</version>
  <description>Auto-generated multi-robot choreography and ROS 2 launch package for {self.workcell_name}</description>
  <maintainer email="dev@roboweaver.ai">RoboWeaver Platform</maintainer>
  <license>Apache-2.0</license>
  <exec_depend>rclpy</exec_depend>
  <exec_depend>std_msgs</exec_depend>
  <exec_depend>trajectory_msgs</exec_depend>
  <exec_depend>geometry_msgs</exec_depend>
  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
"""
        (pkg_dir / "package.xml").write_text(pkg_xml, encoding="utf-8")

        # 6. Save setup.py
        setup_py = f"""from setuptools import setup
import os
from glob import glob

package_name = '{pkg_slug}'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'composite_workcell_bt.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='RoboWeaver',
    maintainer_email='dev@roboweaver.ai',
    description='RoboWeaver Multi-Robot Workcell Package',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={{
        'console_scripts': [
            'robot_agent_node = robot_agent_node:main',
        ],
    }},
)
"""
        (pkg_dir / "setup.py").write_text(setup_py, encoding="utf-8")

        return pkg_dir
