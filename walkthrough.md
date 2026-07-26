# 🚀 RoboWeaver — Universal Multi-Robot Choreography & Prompt-to-System Operating System

We have expanded **RoboWeaver** into a complete **Prompt-to-System Multi-Robot Operating System** capable of building and programming entire multi-robot workcells directly from natural language prompts — featuring **ShopMate-R** as our flagship multi-robot retail assistant demonstration!

---

## 🌟 What Was Accomplished

### 1. Natural Language Prompt-to-System Builder (`PromptToWorkcellBuilder`)
Created `src/roboweaver/fleet/prompt_builder.py` and integrated it with the `roboweaver` CLI:
- **Intelligent Semantic NLP Parser (`SystemPromptParser`)**:
  - Automatically identifies target robot embodiments mentioned in any prompt (`temi`, `pepper`, `franka_panda`, `shadow_hand`, `ur5e`, `kuka_iiwa`, etc.).
  - Decomposes high-level instructions into a choreographed directed acyclic graph (DAG) of task steps and dependencies.
  - Automatically assigns semantic action intents (`MOBILE_NAV`, `HANDOVER_INTERACT`, `PICK_AND_PLACE`, `TIGHTEN_BOLT`, `WELD_SEAM`).
- **Complete System Synthesis (`PromptToWorkcellBuilder.build_from_prompt`)**:
  - Automatically compiles N-DOF motion trajectories for every connected robot in the fleet.
  - Generates the unified Groot2 Composite BehaviorTree XML (`<Sequence>` & `<Parallel>` nodes).
  - Exports a complete, deployable **ROS 2 Multi-Robot Workcell Orchestration Package** (`roboweaver_workcell_<name>`) with multi-namespace `.launch.py` scripts (`/temi`, `/pepper`, `/franka_panda`) and real-time DDS Quality of Service profiles.

### 2. Built-In CLI Command (`roboweaver build` / `roboweaver prompt`)
Added the `build` subcommand to the console CLI in `src/roboweaver/cli/main.py`:
```bash
roboweaver build "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking" --output ./shopmate_r_ws
```

### 3. Flagship ShopMate-R Verification & Test Suite
Created `tests/test_prompt_builder.py` verifying:
- Accurate parsing of **ShopMate-R** (Temi AMR + Pepper Humanoid + Franka Panda Arm).
- Automated compilation of all 6 choreographed tasks.
- Generation of the `roboweaver_workcell_shopmate_r` ROS 2 package with multi-namespace launch configuration.

---

## 🧪 Verification Output

All 3 verification suites pass with **100% success**:

```bash
# 1. Prompt-to-System Builder Verification (ShopMate-R)
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_prompt_builder.py
```
```
=== STARTING ROBOWEAVER PROMPT-TO-SYSTEM BUILDER VERIFICATION ===
  -> Verified ShopMate-R Prompt Parsing (Temi, Pepper, Franka Panda) [PASSED]
  -> Successfully compiled ShopMate-R Workcell & exported ROS 2 package: roboweaver_workcell_shopmate_r [PASSED]
=== ALL PROMPT-TO-SYSTEM BUILDER TESTS PASSED SUCCESSFULLY ===
```

```bash
# 2. Multi-Robot Choreography Verification
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_multi_robot_choreography.py
```
```
=== ALL MULTI-ROBOT CHOREOGRAPHY VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

```bash
# 3. Universal Platform & Code Generator Verification
TMPDIR=/path PYTHONPATH=src python3 -B tests/test_universal_platform.py
```
```
=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY ===
```

---

## 🚀 How to Push to GitHub (`https://github.com/Siddharthpatni/Roboweaver`)

Run the following commands directly in your local terminal:

```bash
cd /Users/siddharthpatni/.gemini/antigravity-ide/scratch/roboweaver

# 1. Stage all prompt builder, choreography, and test files
git add src/roboweaver/hardware/registry_robots.py
git add src/roboweaver/fleet/choreographer.py
git add src/roboweaver/fleet/prompt_builder.py
git add src/roboweaver/fleet/__init__.py
git add src/roboweaver/cli/main.py
git add tests/test_multi_robot_choreography.py
git add tests/test_prompt_builder.py
git add README.md walkthrough.md

# 2. Commit the milestone
git commit -m "feat: add prompt-to-system multi-robot workcell builder with ShopMate-R (Temi, Pepper, Franka) integration"

# 3. Push to GitHub
git push origin main
```

---

## 📢 LinkedIn Ready Announcement Copy

> **"From a single text prompt to a choreographed multi-robot ROS 2 system — open-sourcing RoboWeaver’s Prompt-to-System Builder! 🤖💬"**  
>  
> Ever wanted to connect multiple robots like in **ShopMate-R** (Temi + Pepper + Franka Panda) without spending weeks writing custom ROS 2 scripts and synchronization logic?  
>  
> With **RoboWeaver**, you can now build complete multi-robot workcells with just a text prompt:  
> `roboweaver build "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking" --output ./ros2_ws`  
>  
> 🔥 **What happens under the hood:**  
> • **Semantic NLP & Role Assignment**: Automatically identifies target embodiments (**Temi**, **SoftBank Pepper**, **Franka**, **Shadow Dexterous Hand**, etc.) and assigns optimal semantic intents.  
> • **DAG Schedule & BehaviorTree Synthesis**: Sorts tasks into parallel and sequential execution tiers, generating a unified Groot2 `<Parallel>` and `<Sequence>` Behavior Tree.  
> • **Multi-Namespace ROS 2 Generation**: Synthesizes a ready-to-build ROS 2 package (`roboweaver_workcell_*`) launching `/temi`, `/pepper`, and `/franka_panda` with real-time DDS synchronization topics (`/workcell/sync_token`).  
>  
> Try it yourself:  
> 🔗 **https://github.com/Siddharthpatni/Roboweaver**  
> 🔗 Inspired by **ShopMate-R**: **https://github.com/Siddharthpatni/ShopMate-R**
