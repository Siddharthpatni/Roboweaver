# 🤖 RoboWeaver — Robotics Skill Operating System

> **Compile Robotics Knowledge into Executable, Hardware-Agnostic Intelligence.**  
> *Universal support for ROS 2 (`ros2_control`, MoveIt 2, DDS QoS), physical industrial robots, collaborative arms, and physical simulators (NVIDIA Isaac Sim, Gazebo).*

---

## 🌟 Executive Summary

**RoboWeaver** is a production-grade platform that treats **robot skills** as the fundamental unit of intelligence. It automatically converts fragmented robotics knowledge (natural language instructions, sensor specs, CAD/URDF models, industrial safety guidelines) into **executable, versioned, deployable robot capability packages**.

Unlike traditional frameworks (ROS 2, MoveIt 2) that only provide *infrastructure*, or foundation models that output black-box *policies*, RoboWeaver provides a **complete, transparent skill lifecycle** — from knowledge ingestion and task decomposition through mathematical N-DOF motion planning, behavior tree generation, and real-world execution.

---

## 🔥 Key Breakthrough Capabilities

### 1. 🚀 Universal Skill Taxonomy & Unlimited Plugin System
RoboWeaver goes far beyond basic pick-and-place. It features a built-in industrial & service taxonomy and a **Dynamic Custom Skill Registry (`SkillPluginRegistry`)** that lets you register **any** custom capability on the fly from Python or YAML — zero core code modifications needed.
- **Built-in Industrial Categories**: Pick-and-Place, Bolt Tightening (Torque Control), Arc Welding, Tool Exchange, Surface Inspection, Door Opening, Palletizing, Surface Polishing (Impedance Control), Disassembly, Autonomous Mobile Navigation (SLAM).
- **Dynamic Plugin Loader**: Register specialized skills (e.g., *Surgical Tissue Suturing*, *CNC Machine Tending*, *Semiconductor Wafer Transfer*, *Liquid Pouring*) dynamically.
- **Open-World Fallback**: Automatically synthesizes valid task graphs and BehaviorTrees for arbitrary open-world skills.

### 2. 🌐 Full ROS 2 & `ros2_control` Production Code Generator
RoboWeaver acts as a multi-stage compiler that synthesizes complete, ready-to-build **ROS 2 `rclpy` packages**:
- **ros2_control Controllers**: Pre-configured `JointTrajectoryController`, `JointStateBroadcaster`, `GripperActionController`, and `DiffDriveController`.
- **Industrial DDS QoS Profiles**: High-reliability, transient-local DDS Quality of Service (`dds_qos_profile.yaml`) configured for deterministic real-time control.
- **Lifecycle Action Servers**: Fully wrapped ROS 2 Lifecycle action server nodes with automatic waypoint streaming.
- **MoveIt 2 & Launch Integration**: Auto-generated `.launch.py` scripts and `package.xml` exports for seamless MoveIt 2 integration.

### 3. 🦾 Universal Robot Hardware & Simulation Bridge
RoboWeaver’s **Hardware Abstraction Layer (HAL)** and **`UniversalRobotDriver`** allow any skill to run across heterogeneous robot fleets without rewriting code:
- **Collaborative & Industrial Arms**: Pre-built kinematic profiles for **Franka Emika Panda (7-DOF)**, **Universal Robots UR5e / UR10e (6-DOF)**, **KUKA LBR iiwa 14 R820 (7-DOF)**, **Kinova Gen3 (7-DOF)**, and **ABB IRB 120 (6-DOF)**.
- **Universal Middleware Support**: Connect to physical hardware via **ROS 2 DDS**, or bridge directly to physical simulators including **NVIDIA Isaac Sim**, **Gazebo / Ignition**, and **Webots**.
- **Generalized N-DOF Inverse Kinematics**: Damped least-squares (Levenberg-Marquardt) pseudoinverse solver with nullspace joint-limit avoidance and singularity evasion.
- **Continuous Safety Guard**: ISO 10218 / ISO 15066 compliant velocity clamping, collision envelope checking, and torque-limit verification.

---

## 🏛️ System Architecture

```
                 ┌────────────────────────────────────────────────────────┐
                 │       Natural Language / Knowledge Instruction          │
                 │         "Pick up the heavy gear assembly"              │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 1: Intent Parsing & Semantic Extraction         │
                 │  Action: PICK_AND_PLACE | Target: heavy_gear_assembly  │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 2: Dynamic Task Graph Decomposition             │
                 │  SkillPluginRegistry ──> [PERCEIVE ─> MOVE ─> GRASP...]│
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 3: Generalized N-DOF Kinematics & Safety Guard  │
                 │  Damped Pseudoinverse IK + Nullspace Joint Avoidance   │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 4: Code & Package Generation (ROS 2 / Groot2)    │
                 │  behavior_tree.xml | action_server.py | .launch.py     │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  UniversalRobotDriver (ROS 2 DDS / Isaac Sim / Gazebo)  │
                 │  Franka Panda | UR5e | KUKA iiwa | Kinova Gen3 | ABB    │
                 └────────────────────────────────────────────────────────┘
```

---

## 🚀 Quickstart & Usage

### 1. Installation

```bash
git clone https://github.com/Siddharthpatni/Roboweaver.git
cd Roboweaver
pip install -e .
```

### 2. Compiling a Skill from Natural Language

```python
from roboweaver.compiler import SkillCompiler

# 1. Initialize compiler targeting any supported or custom robot
compiler = SkillCompiler(target_robot="kuka_iiwa")

# 2. Compile instruction into an executable skill package
skill = compiler.compile(
    "Pick up the heavy gear assembly and transfer it to the assembly fixture",
    verbose=True
)

# 3. Inspect generated BehaviorTree & Trajectory Waypoints
print(f"Skill Intent: {skill.intent.action.value} -> {skill.intent.object_name}")
print(f"Total Waypoints: {sum(len(t.waypoints) for t in skill.motion_plan.trajectories.values())}")
```

### 3. Generating a Production ROS 2 Package

```python
from roboweaver.codegen.ros2_gen import generate_ros2_package

# Generate a complete ROS 2 rclpy package ready for `colcon build`
package_path = generate_ros2_package(skill, output_dir="./ros2_ws/src")
print(f"Generated ROS 2 package at: {package_path}")
# Structure:
# ├── package.xml
# ├── setup.py
# ├── behavior_tree.xml
# ├── action_server.py
# ├── config/
# │   ├── dds_qos_profile.yaml
# │   └── ros2_controllers.yaml
# └── launch/
#     └── pick_and_place_heavy_gear_assembly.launch.py
```

### 4. Connecting to Any Physical or Simulated Robot

```python
from roboweaver.hardware.registry_robots import get_robot_spec
from roboweaver.hardware.universal_driver import UniversalRobotDriver

# 1. Retrieve profile for Franka Panda, UR5e, KUKA iiwa, Kinova Gen3, or ABB IRB 120
spec = get_robot_spec("franka_panda")

# 2. Connect via ROS 2 DDS or Simulator Bridge (NVIDIA Isaac Sim / Gazebo)
bridge = UniversalRobotDriver.connect_robot(
    spec=spec,
    protocol="ros2",  # or "sim://isaac_sim"
    uri="ros2://localhost"
)

# 3. Synchronize joint states and stream trajectories
status = bridge.connect()
print(f"Connected: {status.is_connected} | Controllers: {status.active_controllers}")
```

### 5. Registering Custom Skills at Runtime

```python
from roboweaver.skills.taxonomy import SkillPluginRegistry
from roboweaver.types import TaskDecomposition, TaskType, BTNode

# Define custom surgical suturing tasks & behavior tree
suture_tasks = [
    TaskDecomposition(TaskType.PERCEIVE, "Locate wound incision edge"),
    TaskDecomposition(TaskType.MOVE_TO, "Approach insertion waypoint"),
    TaskDecomposition(TaskType.CLOSE_GRIPPER, "Grasp needle", {"force": 2.5}),
    TaskDecomposition(TaskType.MOVE_TO, "Execute helical tissue piercing trajectory"),
]

SkillPluginRegistry.register_template(
    key="SURGERY_SUTURING",
    name="Surgical Tissue Suturing",
    description="Autonomous robotic tissue suturing",
    required_sensors=["stereo_microscope", "micro_ft_sensor"],
    tasks=suture_tasks,
    behavior_tree_root=BTNode("Sequence", "suture_root"),
)
```

---

## 🧪 Verification & Testing

RoboWeaver includes a comprehensive verification suite that validates end-to-end multi-robot connectivity, dynamic skill registration, and ROS 2 package compilation:

```bash
# Run full verification suite
PYTHONPATH=src python3 tests/test_universal_platform.py
```

### Verification Output:
```
=== STARTING ROBOWEAVER UNIVERSAL PLATFORM VERIFICATION ===
[TEST 1] Testing Dynamic Custom Skill Registration...
  -> Successfully registered and retrieved custom skill 'SURGERY_SUTURING' [PASSED]
  -> Successfully generated fallback custom skill template for 'WIPING_TABLE' [PASSED]

[TEST 2] Testing Universal Robot Driver Connection...
  -> Connected & synchronized with [Franka Emika Panda] (7-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Connected & synchronized with [Universal Robots UR5e] (6-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Connected & synchronized with [KUKA LBR iiwa 14 R820] (7-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Connected & synchronized with [Kinova Gen3] (7-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Connected & synchronized with [ABB IRB 120] (6-DOF) via ROS 2 DDS (ros2_control) [PASSED]

[TEST 3] Testing Full ROS 2 Code Generation...
  -> Successfully generated complete ROS 2 package
  -> Verified config/dds_qos_profile.yaml & config/ros2_controllers.yaml [PASSED]
  -> Verified launch file (.launch.py) [PASSED]

[TEST 4] Testing Expanded 16+ Skill Categories...
  -> Verified skill template: [PICK_AND_PLACE ] - Pick and Place [PASSED]
  -> Verified skill template: [TIGHTEN_BOLT   ] - Tighten Bolt [PASSED]
  -> Verified skill template: [OPEN_DOOR      ] - Open Door [PASSED]
  -> Verified skill template: [PALLETIZING    ] - Palletizing [PASSED]
  -> Verified skill template: [POLISHING      ] - Surface Polishing [PASSED]
  -> Verified skill template: [MOBILE_NAV     ] - Mobile Navigation [PASSED]

=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

---

## 📄 License

Licensed under the **Apache License, Version 2.0**. See `LICENSE` for more information.

---

<p align="center">
  <b>Built for the future of Industrial & Autonomous Robotics.</b><br>
  <i>RoboWeaver Platform</i>
</p>
