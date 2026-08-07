"""
Prompt-to-System Multi-Robot Workcell Builder (PromptToWorkcellBuilder).

Converts bounded natural-language workcell prompts into multi-robot schedules and ROS 2
orchestration packages. Only clauses that map to a compiler-supported action become
executable steps; unsupported prose is reported instead of silently becoming PICK.

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

from roboweaver.fleet.choreographer import MultiRobotChoreographer
from roboweaver.ir import CompilerDiagnostic, SkillCompilationError


@dataclass
class ParsedSystemPrompt:
    """Structured workcell specification extracted from a natural language prompt."""
    workcell_name: str
    robots: list[str]
    tasks: list[dict[str, Any]]
    raw_prompt: str
    warnings: list[str] = field(default_factory=list)


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
        (r"(?:card|scan|rfid|badge|barcode|visitor|id\s*card|security|card_scannner|card_scanner)[^,\.;]*", "turtlebot4", "INSPECT_SURFACE"),
        # Navigation / Guide / Mobile
        (r"(?:guide|navigat|transport|driv|lead)\w*[^,\.;]*", "temi", "MOBILE_NAV"),
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

    _CANONICAL_ACTION_PREFIX = {
        "PICK_AND_PLACE": "Pick up workpiece for",
        "MOBILE_NAV": "Navigate to destination described by",
        "INSPECT_SURFACE": "Inspect target described by",
        "TIGHTEN_BOLT": "Tighten M8 bolt described by",
        "WELD_SEAM": "Weld seam described by",
    }

    @classmethod
    def _canonical_instruction(cls, action_type: str, clause: str) -> str | None:
        prefix = cls._CANONICAL_ACTION_PREFIX.get(action_type)
        return f"{prefix}: {clause}" if prefix else None

    @classmethod
    def parse(cls, prompt: str) -> ParsedSystemPrompt:
        """Parse natural language system prompt into a structured multi-robot workcell schedule."""
        lower_prompt = prompt.lower()
        workcell_name = cls._workcell_name(prompt, lower_prompt)
        found_robots = cls._mentioned_robots(lower_prompt)

        # 3. Extract Tasks & Assign to Optimal Robots
        tasks = []
        warnings: list[str] = []
        step_idx = 1
        previous_step_id = None
        last_assigned_robot = None

        # Try splitting by clauses (and, then, comma, semicolon)
        clauses = re.split(r"(?:,|\bwhere\b|\band\b|\bthen\b|\bfor\b|\bwhile\b|\bwith\b|;|\.)", prompt, flags=re.IGNORECASE)
        for clause in clauses:
            clean = clause.strip()
            if len(clean) < 6:
                continue
            if re.match(r"^(?:build|create)\b", clean, re.IGNORECASE):
                continue

            task, warning, last_assigned_robot = cls._parse_clause(
                clean, found_robots, last_assigned_robot, previous_step_id, step_idx,
            )
            if warning:
                warnings.append(warning)
            if task is None:
                continue
            tasks.append(task)
            previous_step_id = task["step_id"]
            step_idx += 1

        # Never invent executable tasks when parsing found none.
        if not tasks:
            warnings.append("No compiler-supported workcell action was found.")

        if not found_robots:
            found_robots = list(dict.fromkeys(t["robot_id"] for t in tasks))

        return ParsedSystemPrompt(
            workcell_name=workcell_name,
            robots=found_robots,
            tasks=tasks,
            raw_prompt=prompt,
            warnings=warnings,
        )

    @staticmethod
    def _workcell_name(prompt: str, lower_prompt: str) -> str:
        name_match = re.search(
            r"(?:build|create|system|project)\s+([a-zA-Z0-9_\-]+)", prompt, re.IGNORECASE,
        )
        if "shopmate" in lower_prompt:
            return "ShopMate_R"
        if "hospital" in lower_prompt or "medical" in lower_prompt:
            return "Hospital_Logistics"
        if name_match and len(name_match.group(1)) > 2:
            return name_match.group(1).replace("-", "_").capitalize()
        return "Universal_Workcell"

    @classmethod
    def _mentioned_robots(cls, lower_prompt: str) -> list[str]:
        return list(dict.fromkeys(
            robot_id
            for keyword, robot_id in cls.ROBOT_KEYWORDS.items()
            if re.search(r"\b" + keyword + r"\b", lower_prompt)
        ))

    @classmethod
    def _parse_clause(
        cls,
        clean: str,
        found_robots: list[str],
        last_assigned_robot: str | None,
        previous_step_id: str | None,
        step_index: int,
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        assigned_robot = next((
            robot_id for keyword, robot_id in cls.ROBOT_KEYWORDS.items()
            if re.search(r"\b" + keyword + r"\b", clean.lower())
        ), None)
        last_assigned_robot = assigned_robot or last_assigned_robot
        match = next((
            (default_robot, action_type)
            for pattern, default_robot, action_type in cls.TASK_PATTERNS
            if re.search(pattern, clean, re.IGNORECASE)
        ), None)
        if match is None:
            return None, f"Skipped clause with no supported action: {clean}", last_assigned_robot
        default_robot, action_type = match
        assigned_robot = assigned_robot or last_assigned_robot or default_robot
        if assigned_robot not in found_robots:
            found_robots.append(assigned_robot)
        instruction = cls._canonical_instruction(action_type, clean)
        if instruction is None:
            return None, f"Skipped unsupported workcell action {action_type}: {clean}", last_assigned_robot
        step_id = f"step_{step_index}_{assigned_robot}"
        handover_target = None
        if re.search(r"\bhand\s*over\b|\btransfer\b|\breceiv\w*\b", clean, re.IGNORECASE):
            handover_target = next(
                (robot_id for robot_id in found_robots if robot_id != assigned_robot), None,
            )
        return {
            "step_id": step_id,
            "robot_id": assigned_robot,
            "instruction": instruction,
            "source_clause": clean,
            "depends_on": [previous_step_id] if previous_step_id else [],
            "handover_target": handover_target,
            "action": action_type,
        }, None, last_assigned_robot


class PromptToWorkcellBuilder:
    """Build a checked schedule and orchestration package from a bounded prompt."""

    @classmethod
    def build_from_prompt(
        cls,
        prompt: str,
        output_dir: str | Path | None = None,
        verbose: bool = True,
    ) -> tuple[MultiRobotChoreographer, Path | None]:
        """Parse supported clauses, compile every retained skill, and package the schedule."""
        parsed = SystemPromptParser.parse(prompt)

        if not parsed.tasks:
            raise SkillCompilationError([
                CompilerDiagnostic(
                    code="RW101",
                    severity="error",
                    message="The workcell prompt contains no supported executable task.",
                    reason="; ".join(parsed.warnings),
                    required_capability=None,
                    fixes=[
                        "Assign each robot an explicit supported action and target.",
                        "Treat conversation, speech, and social interaction as planned "
                        "capabilities until a typed backend is implemented.",
                    ],
                )
            ])

        if verbose:
            print("\n\033[1;35m━━━ RoboWeaver Prompt-to-System Builder ━━━\033[0m")
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
                print("\n  \033[1;32m✓ SYSTEM BUILT SUCCESSFULLY\033[0m")
                print(f"  ROS 2 Orchestration Package : \033[36m{pkg_path}\033[0m")
                print(f"  BehaviorTree XML            : {pkg_path / 'composite_workcell_bt.xml'}")
                print(f"  Launch Script               : {pkg_path / 'launch/workcell_orchestration.launch.py'}\n")

        return choreographer, pkg_path
