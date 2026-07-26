# 🤖 RoboWeaver — Robotics Skill Operating System

> **Compile Robotics Knowledge into Executable, Hardware-Agnostic Intelligence & Multi-Robot Workcell Choreography.**  
> *Universal support for ROS 2 (`ros2_control`, MoveIt 2, DDS QoS), heterogeneous multi-robot fleets (Temi, Pepper, Dexterous Hands, Industrial Arms), and physical simulators (NVIDIA Isaac Sim, Gazebo).*

---

## 🌟 Executive Summary

**RoboWeaver** is a production-grade platform that treats **robot skills** as the fundamental unit of intelligence. It automatically converts fragmented robotics knowledge (natural language instructions, sensor specs, CAD/URDF models, industrial safety guidelines) into **executable, versioned, deployable robot capability packages** and **choreographed multi-robot workcells**.

Unlike traditional frameworks (ROS 2, MoveIt 2) that only provide *infrastructure*, or foundation models that output black-box *policies*, RoboWeaver provides a **complete, transparent skill lifecycle** — from knowledge ingestion and task decomposition through mathematical N-DOF motion planning, multi-robot DAG scheduling, behavior tree generation, and real-world execution.

---

## 🔥 Key Breakthrough Capabilities

### 1. 🦾 Heterogeneous Multi-Robot Workcell Choreography (`MultiRobotChoreographer`)
RoboWeaver is not limited to single-arm tasks. It can choreograph complete **multi-robot workcells** where service robots, humanoids, mobile manipulators, and dexterous hands collaborate:
- **Service & Social Mobile Robots**: Built-in profiles for **Temi Service Robot** (3-DOF AMR with display & sensor array) and **SoftBank Pepper Humanoid** (17-DOF mobile humanoid with dual arms).
- **Dexterous Robotic Hands**: Anthropomorphic **Shadow Dexterous Hand (20-DOF)** and **Robotiq 3-Finger Adaptive Hand (4-DOF)** for precision multi-finger manipulation.
- **Industrial & Cobot Arms**: **Franka Emika Panda (7-DOF)**, **Universal Robots UR5e / UR10e (6-DOF)**, **KUKA LBR iiwa 14 R820 (7-DOF)**, **Kinova Gen3 (7-DOF)**, and **ABB IRB 120 (6-DOF)**.
- **DAG Task Scheduling & Parallel Execution**: Automatically sorts multi-robot dependency graphs into parallel and sequential execution tiers, synthesizing unified Groot2 `<Parallel>` and `<Sequence>` Behavior Trees.
- **Multi-Namespace ROS 2 Launch Package**: Generates complete ROS 2 orchestration packages (`roboweaver_workcell_*`) launching each robot in its own ROS 2 namespace (`/temi`, `/pepper`, `/shadow_hand`, `/franka_panda`) with inter-robot DDS synchronization topics (`/workcell/sync_token`).

### 2. 🚀 Universal Skill Taxonomy & Unlimited Plugin System
RoboWeaver features a built-in industrial & service taxonomy and a **Dynamic Custom Skill Registry (`SkillPluginRegistry`)** that lets you register **any** custom capability on the fly from Python or YAML — zero core code modifications needed.
- **Built-in Industrial Categories**: Pick-and-Place, Bolt Tightening (Torque Control), Arc Welding, Tool Exchange, Surface Inspection, Door Opening, Palletizing, Surface Polishing (Impedance Control), Disassembly, Autonomous Mobile Navigation (SLAM).
- **Dynamic Plugin Loader**: Register specialized skills (e.g., *Surgical Tissue Suturing*, *CNC Machine Tending*, *Semiconductor Wafer Transfer*, *Liquid Pouring*) dynamically.
- **Open-World Fallback**: Automatically synthesizes valid task graphs and BehaviorTrees for arbitrary open-world skills.

### 3. 🌐 Full ROS 2 & `ros2_control` Production Code Generator
RoboWeaver acts as a multi-stage compiler that synthesizes complete, ready-to-build **ROS 2 `rclpy` packages**:
- **ros2_control Controllers**: Pre-configured `JointTrajectoryController`, `JointStateBroadcaster`, `GripperActionController`, and `DiffDriveController`.
- **Industrial DDS QoS Profiles**: High-reliability, transient-local DDS Quality of Service (`dds_qos_profile.yaml`) configured for deterministic real-time control.
- **Lifecycle Action Servers**: Fully wrapped ROS 2 Lifecycle action server nodes with automatic waypoint streaming.
- **MoveIt 2 & Launch Integration**: Auto-generated `.launch.py` scripts and `package.xml` exports for seamless MoveIt 2 integration.

### 4. 🔗 Universal Robot Hardware & Simulation Bridge
RoboWeaver’s **Hardware Abstraction Layer (HAL)** and **`UniversalRobotDriver`** allow any skill to run across heterogeneous robot fleets without rewriting code:
- **Universal Middleware Support**: Connect to physical hardware via **ROS 2 DDS**, or bridge directly to physical simulators including **NVIDIA Isaac Sim**, **Gazebo / Ignition**, and **Webots**.
- **Generalized N-DOF Inverse Kinematics**: Damped least-squares (Levenberg-Marquardt) pseudoinverse solver with nullspace joint-limit avoidance and singularity evasion.
- **Continuous Safety Guard**: ISO 10218 / ISO 15066 compliant velocity clamping, collision envelope checking, and torque-limit verification.

---

## 🏛️ System Architecture

```
                 ┌────────────────────────────────────────────────────────┐
                 │       Multi-Robot System Instruction / Workcell        │
                 │   "Hospital Logistics: Temi -> Pepper -> Shadow Hand"  │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 1: Multi-Robot DAG Scheduling & Tier Sorting    │
                 │  Tier 1: Temi Nav ─> Tier 2: Pepper Handover ─> Tier 3 │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 2: Per-Robot N-DOF Compilation & Kinematics     │
                 │  Temi (3-DOF) | Pepper (17-DOF) | Shadow Hand (20-DOF) │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 3: Composite Groot2 <Parallel> & <Sequence> BT   │
                 │  Synchronized BehaviorTree XML across all Namespaces   │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  Stage 4: Multi-Namespace ROS 2 Orchestration Package   │
                 │  /temi | /pepper | /shadow_hand | /franka_panda DDS    │
                 └───────────────────────────┬────────────────────────────┘
                                             ▼
                 ┌────────────────────────────────────────────────────────┐
                 │  UniversalRobotDriver (ROS 2 DDS / Isaac Sim / Gazebo)  │
                 │  Temi | Pepper | Shadow Hand | Robotiq Hand | Franka    │
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

### 2. Prompt-to-System Builder (`ShopMate-R` Multi-Robot Workcell Demo)

You can build complete multi-robot systems directly from a natural language prompt using the CLI or Python SDK:

#### Using the CLI:
```bash
roboweaver build "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking" --output ./ros2_ws/src
```
**Output:**
```
━━━ RoboWeaver Prompt-to-System Builder ━━━
  Input Prompt  : "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
  System Name   : ShopMate_R
  Robot Fleet   : temi, pepper, franka_panda (3 connected robots)
  Task Schedule : 6 choreographed steps

  ✓ SYSTEM BUILT SUCCESSFULLY
  ROS 2 Orchestration Package : ./ros2_ws/src/roboweaver_workcell_shopmate_r
  BehaviorTree XML            : ./ros2_ws/src/roboweaver_workcell_shopmate_r/composite_workcell_bt.xml
  Launch Script               : ./ros2_ws/src/roboweaver_workcell_shopmate_r/launch/workcell_orchestration.launch.py
```

#### Using Python (`PromptToWorkcellBuilder`):
```python
from roboweaver.fleet import PromptToWorkcellBuilder

prompt = "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
choreographer, package_path = PromptToWorkcellBuilder.build_from_prompt(
    prompt=prompt,
    output_dir="./shopmate_r_ws/src",
    verbose=True,
)
```

### 3. Building a Multi-Robot Workcell Choreography Manually
```python
from roboweaver.fleet import MultiRobotChoreographer

# 1. Initialize Multi-Robot Choreographer for a Hospital Logistics Workcell
choreographer = MultiRobotChoreographer(workcell_name="Hospital_Logistics")

# 2. Add choreographed tasks across Temi, Pepper, Shadow Hand, and Franka Panda
choreographer.add_robot_task(
    step_id="step_1_temi_nav",
    robot_id="temi",
    instruction="Navigate to pharmacy storage shelf",
)

choreographer.add_robot_task(
    step_id="step_2_pepper_handover",
    robot_id="pepper",
    instruction="Receive vial tray from Temi and greet medical staff",
    depends_on=["step_1_temi_nav"],
    handover_target="pepper",
)

# Parallel execution tier: Shadow Hand and Franka Panda execute simultaneously
choreographer.add_robot_task(
    step_id="step_3_shadow_hand_grasp",
    robot_id="shadow_hand",
    instruction="Grasp medical vial with 20-DOF tactile fingertips",
    depends_on=["step_2_pepper_handover"],
)

choreographer.add_robot_task(
    step_id="step_4_franka_inspect",
    robot_id="franka_panda",
    instruction="Inspect surface of vial under microscope",
    depends_on=["step_2_pepper_handover"],
)

# 3. Compile all N-DOF robot skills and compute parallel execution tiers
schedule = choreographer.compile_workcell(verbose=True)
```

### 3. Generating a Multi-Robot ROS 2 Orchestration Package

```python
# Generate a complete multi-namespace ROS 2 package ready for `colcon build`
package_path = choreographer.export_workcell_ros2_package(output_dir="./ros2_ws/src")
print(f"Generated Multi-Robot ROS 2 package at: {package_path}")
# Structure:
# ├── package.xml
# ├── setup.py
# ├── composite_workcell_bt.xml  (<Sequence> & <Parallel> synchronized nodes)
# ├── robot_agent_node.py
# ├── config/
# │   └── inter_robot_dds.yaml   (/workcell/sync_token QoS configuration)
### 4. Inspire Robots Dexterous Hand RH56F1-E2 (RS485) Driver & ROS 2 Pipeline

RoboWeaver includes built-in driver and ROS 2 support for the commercial **6-DOF Inspire Hand RH56F1-E2** over RS485 Modbus RTU (`/dev/ttyUSB0` @ 115200 baud):

```python
from roboweaver.hardware import InspireHandRS485Driver
from roboweaver.codegen import generate_inspire_hand_ros2_package

# 1. Direct Python RS485 Control & Gesture Library
driver = InspireHandRS485Driver(port="/dev/ttyUSB0", baudrate=115200)
driver.connect()

# Execute dexterous grasping postures
driver.set_gesture("fist")
driver.set_gesture("pinch")
driver.set_gesture("precision_grip")
driver.set_gesture("open")

# 2. Export Standalone ROS 2 Package with Action Server & ros2_control
pkg_path = generate_inspire_hand_ros2_package(output_dir="./ros2_ws/src")
print(f"Generated Inspire Hand ROS 2 package at: {pkg_path}")
```

### 5. Compiling an Individual Skill for Any Robot

```python
from roboweaver.compiler import SkillCompiler

# Compile instruction targeting KUKA LBR iiwa (or 'temi', 'pepper', 'shadow_hand', etc.)
compiler = SkillCompiler(target_robot="kuka_iiwa")
skill = compiler.compile("Pick up the heavy gear assembly", verbose=True)
print(f"Compiled for: {compiler.robot_spec.name} ({compiler.robot_spec.dof}-DOF)")
```

---

## 🧪 Verification & Testing

RoboWeaver includes comprehensive verification suites validating multi-robot choreography, heterogeneous robot connectivity, dynamic skill registration, and ROS 2 package compilation:

```bash
# 1. Run Multi-Robot Choreography Suite (Temi, Pepper, Shadow Hand, Franka)
PYTHONPATH=src python3 tests/test_multi_robot_choreography.py

# 2. Run Full Universal Platform Suite (Dynamic Skills, ROS 2 Generators, IK)
PYTHONPATH=src python3 tests/test_universal_platform.py
```

### Verification Output:
```
=== STARTING ROBOWEAVER MULTI-ROBOT CHOREOGRAPHY VERIFICATION ===
[TEST 1] Testing Heterogeneous Robot Profiles (Temi, Pepper, Dexterous Hands)...
  -> Verified & Connected: [Temi Service Robot            ] (3-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Verified & Connected: [SoftBank Pepper Humanoid      ] (17-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Verified & Connected: [Shadow Dexterous Hand         ] (20-DOF) via ROS 2 DDS (ros2_control) [PASSED]
  -> Verified & Connected: [Robotiq 3-Finger Adaptive Hand] (4-DOF) via ROS 2 DDS (ros2_control) [PASSED]

[TEST 2] Testing Multi-Robot Choreography Pipeline (Hospital Logistics Workcell)...
  -> Compiled all 6 choreographed tasks across Temi, Pepper, Shadow Hand, and Franka [PASSED]
  -> Successfully computed 5 execution tiers (Tier 5 contains 2 parallel tasks: shadow_hand & franka_panda) [PASSED]
  -> Generated composite Groot2 BehaviorTree XML with synchronized <Parallel> & <Sequence> nodes [PASSED]
  -> Generated Multi-Robot ROS 2 Launch Package: [roboweaver_workcell_hospital_logistics]
  -> Verified multi-namespace launch script (/temi, /pepper, /shadow_hand, /franka_panda) [PASSED]
  -> Verified config/inter_robot_dds.yaml & composite_workcell_bt.xml [PASSED]

=== ALL MULTI-ROBOT CHOREOGRAPHY VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

---

## 📄 License

Licensed under the **Apache License, Version 2.0**. See `LICENSE` for more information.

---

<p align="center">
  <b>Built for the future of Industrial & Autonomous Robotics.</b><br>
  <i>RoboWeaver Platform</i>
</p>
