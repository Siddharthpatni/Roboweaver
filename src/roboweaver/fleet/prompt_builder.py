"""
Prompt-to-System Multi-Robot Workcell Builder (PromptToWorkcellBuilder).

Converts natural language prompts directly into complete, multi-robot choreographed systems
and production-ready ROS 2 packages.

Examples:
- "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
- "Build hospital logistics workcell with Temi AMR, Pepper humanoid, and Shadow Dexterous Hand"
- "Build automated factory line with UR5e for pick and place, KUKA for bolt tightening, and ABB for welding"
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from roboweaver.hardware import get_robot_spec, ROBOT_REGISTRY
from roboweaver.fleet.choreographer import MultiRobotChoreographer, WorkcellSchedule


@dataclass
class ParsedSystemPrompt:
    """Structured workcell specification extracted from a natural language prompt."""
    workcell_name: str
    robots: list[str]
    tasks: list[dict[str, Any]]
    raw_prompt: str


class SystemPromptParser:
    """Intelligent NLP & semantic keyword parser for multi-robot system prompts."""

    ROBOT_KEYWORDS = {
        "temi": "temi",
        "pepper": "pepper",
        "shadow_hand": "shadow_hand",
        "shadow": "shadow_hand",
        "robotiq": "robotiq_hand",
        "inspire_hand": "inspire_hand_rh56f1_e2",
        "inspire": "inspire_hand_rh56f1_e2",
        "rh56f1": "inspire_hand_rh56f1_e2",
        "rh56f1_e2": "inspire_hand_rh56f1_e2",
        "franka": "franka_panda",
        "panda": "franka_panda",
        "ur5e": "ur5e",
        "ur10e": "ur10e",
        "kuka": "kuka_iiwa",
        "iiwa": "kuka_iiwa",
        "kinova": "kinova_gen3",
        "abb": "abb_irb120",
        "turtlebot": "turtlebot4",
        "turtlebot4": "turtlebot4",
        "turtlebot3": "turtlebot4",
        "card_scanner": "turtlebot4",
        "card_scannner": "turtlebot4",
    }

    TASK_PATTERNS = [
        # Card Scanning / RFID / Security / Visitor Badge / Mobile Card Scanner
        (r"(?:card|scan|rfid|badge|barcode|visitor|id\s*card|security|card_scannner|card_scanner)[^,\.;]*", "turtlebot4", "MOBILE_NAV"),
        # Navigation / Guide / Mobile
        (r"(?:guide|navigat|mov|transport|driv|lead)\w*\s+(?:to|customer|item|shelf|aisle|patient|vial|station|storage)[^,\.;]*", "temi", "MOBILE_NAV"),
        # Interaction / Handover / Greet / Answer / Assist
        (r"(?:answer|greet|hand\s*over|assist|interact|receiv|customer|staff|doctor|product\s*question)[^,\.;]*", "pepper", "HANDOVER_INTERACT"),
        # Dexterous grasping / manipulation with hand
        (r"(?:dexterous|pinch|fist|cylindrical|inspire|rh56f1|finger|precision\s*grip)[^,\.;]*", "inspire_hand_rh56f1_e2", "PICK_AND_PLACE"),
        # Restock / Pick / Place / Grasp / Assemble
        (r"(?:restock|pick|place|grasp|shelf|top\s*shelf|item|box|assembly|vial)[^,\.;]*", "franka_panda", "PICK_AND_PLACE"),
        # Tighten bolt
        (r"(?:tighten|bolt|torque|screw)[^,\.;]*", "kuka_iiwa", "TIGHTEN_BOLT"),
        # Weld
        (r"(?:weld|seam|arc)[^,\.;]*", "abb_irb120", "WELD_SEAM"),
    ]

    @classmethod
    def parse(cls, prompt: str) -> ParsedSystemPrompt:
        """Parse natural language system prompt into a structured multi-robot workcell schedule."""
        lower_prompt = prompt.lower()

        # 1. Deduce Workcell Name
        name_match = re.search(r"(?:build|create|system|project)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE)
        if "shopmate" in lower_prompt:
            workcell_name = "ShopMate_R"
        elif "hospital" in lower_prompt or "medical" in lower_prompt:
            workcell_name = "Hospital_Logistics"
        elif name_match and len(name_match.group(1)) > 2:
            workcell_name = name_match.group(1).replace("-", "_").capitalize()
        else:
            workcell_name = "Universal_Workcell"

        # 2. Extract Mentioned Robots
        found_robots = []
        for kw, robot_id in cls.ROBOT_KEYWORDS.items():
            if re.search(r"\b" + kw + r"\b", lower_prompt):
                if robot_id not in found_robots:
                    found_robots.append(robot_id)

        # 3. Extract Tasks & Assign to Optimal Robots
        tasks = []
        step_idx = 1
        previous_step_id = None

        # Try splitting by clauses (and, then, comma, semicolon)
        clauses = re.split(r"(?:,|\bwhere\b|\band\b|\bthen\b|\bfor\b|\bwhile\b|\bwith\b|;|\.)", prompt, flags=re.IGNORECASE)
        for clause in clauses:
            clean = clause.strip()
            if len(clean) < 6:
                continue

            # Identify which robot is in this clause
            assigned_robot = None
            for kw, r_id in cls.ROBOT_KEYWORDS.items():
                if re.search(r"\b" + kw + r"\b", clean.lower()):
                    assigned_robot = r_id
                    break

            # Deduce action type and fallback robot from TASK_PATTERNS
            action_type = "PICK_AND_PLACE"
            for pat, def_robot, a_type in cls.TASK_PATTERNS:
                if re.search(pat, clean, re.IGNORECASE):
                    action_type = a_type
                    if not assigned_robot:
                        assigned_robot = def_robot
                        if assigned_robot not in found_robots:
                            found_robots.append(assigned_robot)
                    break

            if not assigned_robot:
                # Default fallback to first found robot or generic 6dof
                assigned_robot = found_robots[0] if found_robots else "franka_panda"

            step_id = f"step_{step_idx}_{assigned_robot}"
            depends_on = [previous_step_id] if previous_step_id else []
            handover_target = None
            if "hand" in clean.lower() or "transfer" in clean.lower() or "receiv" in clean.lower():
                # Check if handing over to another robot
                for r_id in found_robots:
                    if r_id != assigned_robot:
                        handover_target = r_id
                        break

            tasks.append({
                "step_id": step_id,
                "robot_id": assigned_robot,
                "instruction": clean.capitalize(),
                "depends_on": depends_on,
                "handover_target": handover_target,
                "action": action_type,
            })
            previous_step_id = step_id
            step_idx += 1

        # Fallback if prompt was too brief to split into clauses
        if not tasks:
            for r_id in (found_robots or ["temi", "pepper", "franka_panda"]):
                step_id = f"step_{step_idx}_{r_id}"
                depends_on = [previous_step_id] if previous_step_id else []
                tasks.append({
                    "step_id": step_id,
                    "robot_id": r_id,
                    "instruction": f"Execute automated task for {r_id}",
                    "depends_on": depends_on,
                    "handover_target": None,
                    "action": "MOBILE_NAV" if "turtlebot" in r_id or "temi" in r_id else "PICK_AND_PLACE",
                })
                previous_step_id = step_id
                step_idx += 1

        if not found_robots:
            found_robots = list(dict.fromkeys(t["robot_id"] for t in tasks))

        return ParsedSystemPrompt(
            workcell_name=workcell_name,
            robots=found_robots,
            tasks=tasks,
            raw_prompt=prompt,
        )


class PromptToWorkcellBuilder:
    """Builds a complete multi-robot system and ROS 2 package from a natural language prompt."""

    @classmethod
    def build_from_prompt(
        cls,
        prompt: str,
        output_dir: str | Path | None = None,
        verbose: bool = True,
    ) -> tuple[MultiRobotChoreographer, Path | None]:
        """Parse prompt, build choreographer schedule, compile all skills, and generate ROS 2 package."""
        parsed = SystemPromptParser.parse(prompt)

        if verbose:
            print(f"\n\033[1;35m━━━ RoboWeaver Prompt-to-System Builder ━━━\033[0m")
            print(f"  Input Prompt  : \033[1m\"{prompt}\"\033[0m")
            print(f"  System Name   : \033[36m{parsed.workcell_name}\033[0m")
            print(f"  Robot Fleet   : \033[32m{', '.join(parsed.robots)}\033[0m ({len(parsed.robots)} connected robots)")
            print(f"  Task Schedule : {len(parsed.tasks)} choreographed steps")

        choreographer = MultiRobotChoreographer(workcell_name=parsed.workcell_name)

        for t in parsed.tasks:
            choreographer.add_robot_task(
                step_id=t["step_id"],
                robot_id=t["robot_id"],
                instruction=t["instruction"],
                depends_on=t["depends_on"],
                handover_target=t["handover_target"],
            )

        # Compile all skills in the workcell
        choreographer.compile_workcell(verbose=verbose)

        # Generate ROS 2 multi-namespace package if output_dir is provided
        pkg_path = None
        if output_dir:
            pkg_path = choreographer.export_workcell_ros2_package(output_dir)
            if verbose:
                print(f"\n  \033[1;32m✓ SYSTEM BUILT SUCCESSFULLY\033[0m")
                print(f"  ROS 2 Orchestration Package : \033[36m{pkg_path}\033[0m")
                print(f"  BehaviorTree XML            : {pkg_path / 'composite_workcell_bt.xml'}")
                print(f"  Launch Script               : {pkg_path / 'launch/workcell_orchestration.launch.py'}\n")

        return choreographer, pkg_path
