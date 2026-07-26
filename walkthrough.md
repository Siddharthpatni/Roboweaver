# 🚀 RoboWeaver — Universal Multi-Robot Choreography & Prompt-to-System Operating System

We have expanded **RoboWeaver** into a complete **Prompt-to-System Multi-Robot Operating System** capable of building and programming entire multi-robot workcells directly from natural language prompts — featuring **ShopMate-R** and the **Inspire Robots Dexterous Hand RH56F1-E2 (RS485)** as our flagship demonstrations!

---

## 🌟 What Was Accomplished

### 1. Inspire Robots Dexterous Hand RH56F1-E2 (RS485) Pipeline
Created an end-to-end industrial driver, gesture library, and ROS 2 generator for the **Inspire RH56F1-E2**:
- **Hardware Profile & Registry (`get_inspire_hand_spec()` in `registry_robots.py`)**:
  - Full 6-DOF / 6-Actuator anthropomorphic dexterous hand profile (`thumb_flex`, `thumb_abduct`, `index_flex`, `middle_flex`, `ring_flex`, `pinky_flex`).
- **RS485 Communication Driver & Gesture Library (`InspireHandRS485Driver` in `inspire_hand_rs485.py`)**:
  - Modbus RTU / RS485 serial packet framing over `/dev/ttyUSB0` @ `115200` baud.
  - Multi-actuator position (0–1000) and proportional grasping force simulation.
  - Pre-programmed dexterous grasping postures: `"open"`, `"fist"`, `"pinch"`, `"precision_grip"`, `"cylindrical_grip"`, `"relax"`.
  - High-fidelity loopback simulation fallback when physical serial hardware is absent.
- **Standalone ROS 2 Package Generator (`generate_inspire_hand_ros2_package` in `inspire_ros2_gen.py`)**:
  - Exports a complete ROS 2 package (`roboweaver_inspire_hand_rh56f1`) with:
    - `/inspire_hand_action_server.py`: Action server for actuator commands and gesture commands.
    - `/config/inspire_rh56f1_controllers.yaml`: `ros2_control` position and force controller configuration.
    - `/launch/inspire_hand_rs485.launch.py`: ROS 2 launch script parameterized for serial port and baudrate.
- **Prompt-to-System Integration**:
  - Users can now type natural language prompts mentioning `"inspire"`, `"inspire_hand"`, or `"rh56f1"` to automatically generate multi-robot ROS 2 workcells.

### 2. Natural Language Prompt-to-System Builder (`PromptToWorkcellBuilder`)
Created `src/roboweaver/fleet/prompt_builder.py` and integrated it with the `roboweaver` CLI:
- **Intelligent Semantic NLP Parser (`SystemPromptParser`)**:
  - Automatically identifies target robot embodiments mentioned in any prompt (`temi`, `pepper`, `franka_panda`, `shadow_hand`, `inspire_hand_rh56f1_e2`, `ur5e`, `kuka_iiwa`, etc.).
  - Decomposes high-level instructions into a choreographed directed acyclic graph (DAG) of task steps and dependencies.

---

## 🧪 Verification Output

All 4 verification suites pass with **100% success**:

```bash
# 1. Inspire RH56F1-E2 (RS485) Verification
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_inspire_hand_rs485.py
```
```
=== STARTING ROBOWEAVER INSPIRE RH56F1-E2 (RS485) VERIFICATION ===
[TEST 1] Testing Inspire RH56F1-E2 (RS485) Hardware Specification...
  -> Verified Specification: [Inspire Hand RH56F1-E2] (6-DOF) [PASSED]
[TEST 2] Testing Inspire RH56F1-E2 RS485 Driver & Gesture Library...
  -> Verified 6-Actuator Position & Grasping Force simulation [PASSED]
  -> Verified Dexterous Gesture Library (fist, pinch, precision_grip, cylindrical_grip, open) [PASSED]
[TEST 3] Testing Inspire RH56F1-E2 ROS 2 Package Generation...
  -> Successfully generated ROS 2 package: [roboweaver_inspire_hand_rh56f1] [PASSED]
  -> Verified ros2_control YAML (/config/inspire_rh56f1_controllers.yaml) [PASSED]
  -> Verified RS485 action server (/inspire_hand_action_server.py) [PASSED]
[TEST 4] Testing Prompt-to-System Integration for Inspire RH56F1-E2...
  -> Verified Prompt-to-Workcell Multi-Robot Package with Inspire Hand [PASSED]
=== ALL INSPIRE RH56F1-E2 VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

```bash
# 2. Prompt-to-System Builder Verification (ShopMate-R)
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_prompt_builder.py
```
```
=== ALL PROMPT-TO-SYSTEM BUILDER TESTS PASSED SUCCESSFULLY ===
```

```bash
# 3. Multi-Robot Choreography Verification
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_multi_robot_choreography.py
```
```
=== ALL MULTI-ROBOT CHOREOGRAPHY VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

---

## 🚀 How to Push to GitHub (`https://github.com/Siddharthpatni/Roboweaver`)

Run the following commands directly in your local terminal:

```bash
cd /Users/siddharthpatni/.gemini/antigravity-ide/scratch/roboweaver

# 1. Stage all new Inspire Hand driver, codegen, and test files
git add src/roboweaver/hardware/inspire_hand_rs485.py
git add src/roboweaver/hardware/registry_robots.py
git add src/roboweaver/hardware/__init__.py
git add src/roboweaver/codegen/inspire_ros2_gen.py
git add src/roboweaver/codegen/__init__.py
git add src/roboweaver/fleet/prompt_builder.py
git add tests/test_inspire_hand_rs485.py
git add README.md walkthrough.md

# 2. Commit the milestone
git commit -m "feat: add Inspire Robots RH56F1-E2 dexterous hand RS485 driver, gesture library, and ROS 2 pipeline"

# 3. Push to GitHub
git push origin main
```
