"""
Universal Industrial & Service Robot Skill Taxonomy & Dynamic Plugin Registry.

Supports built-in industrial/service capability templates as well as dynamic
user-registered custom skill templates from YAML/JSON or Python code.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from roboweaver.types import Action, TaskDecomposition, TaskType, BTNode


class IndustrialSkillCategory(Enum):
    # Built-in Core Industrial Skills
    PICK_AND_PLACE = "PICK_AND_PLACE"
    TIGHTEN_BOLT = "TIGHTEN_BOLT"
    OPEN_DOOR = "OPEN_DOOR"
    TOOL_EXCHANGE = "TOOL_EXCHANGE"
    INSPECT_SURFACE = "INSPECT_SURFACE"
    WELD_SEAM = "WELD_SEAM"

    # Expanded Advanced Robotics & Service Skills
    PALLETIZING = "PALLETIZING"
    POLISHING = "POLISHING"
    DISASSEMBLY = "DISASSEMBLY"
    MOBILE_NAV = "MOBILE_NAV"
    PEGGING = "PEGGING"
    POURING_LIQUID = "POURING_LIQUID"
    PACKAGING = "PACKAGING"
    CNC_LOADING = "CNC_LOADING"
    SURGERY_ASSIST = "SURGERY_ASSIST"
    SORTING = "SORTING"
    CLEANING = "CLEANING"
    CUSTOM_SKILL = "CUSTOM_SKILL"


@dataclass
class IndustrialSkillTemplate:
    category: IndustrialSkillCategory | str
    name: str
    description: str
    required_sensors: list[str]
    tasks: list[TaskDecomposition]
    behavior_tree_root: BTNode


class SkillPluginRegistry:
    """Dynamic registry for custom robot skill templates and plugins."""

    _custom_templates: dict[str, IndustrialSkillTemplate] = {}

    @classmethod
    def register_template(
        cls,
        key: str,
        name: str,
        description: str,
        required_sensors: list[str],
        tasks: list[TaskDecomposition],
        behavior_tree_root: BTNode,
    ) -> None:
        """Register a custom skill template dynamically at runtime."""
        cls._custom_templates[key.upper()] = IndustrialSkillTemplate(
            category=key.upper(),
            name=name,
            description=description,
            required_sensors=required_sensors,
            tasks=tasks,
            behavior_tree_root=behavior_tree_root,
        )

    @classmethod
    def load_from_json(cls, json_path: str | Path) -> int:
        """Load custom skill templates from a JSON/YAML specification file."""
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        count = 0
        for item in data.get("skills", []):
            tasks = [
                TaskDecomposition(
                    task_type=TaskType(t["type"]),
                    description=t["description"],
                    parameters=t.get("parameters", {}),
                )
                for t in item.get("tasks", [])
            ]
            bt_children = [
                BTNode(c.get("node_type", "Action"), c["name"])
                for c in item.get("bt_children", [])
            ]
            bt = BTNode("Sequence", f"{item['key'].lower()}_root", children=bt_children)

            cls.register_template(
                key=item["key"],
                name=item["name"],
                description=item["description"],
                required_sensors=item.get("required_sensors", []),
                tasks=tasks,
                behavior_tree_root=bt,
            )
            count += 1
        return count

    @classmethod
    def get_template(cls, key: str) -> IndustrialSkillTemplate | None:
        return cls._custom_templates.get(key.upper())

    @classmethod
    def list_custom_skills(cls) -> list[str]:
        return list(cls._custom_templates.keys())


def get_industrial_skill_template(
    category: IndustrialSkillCategory | str, target_name: str = "object"
) -> IndustrialSkillTemplate:
    """Retrieve structured task graph and BT for industrial or custom skill category."""

    # 1. Check custom registered plugins first
    if isinstance(category, str):
        custom = SkillPluginRegistry.get_template(category)
        if custom:
            return custom
        # Try converting str to enum
        try:
            category = IndustrialSkillCategory(category.upper())
        except ValueError:
            # Fallback for arbitrary custom string skills
            return _create_generic_custom_template(category, target_name)

    if category == IndustrialSkillCategory.PICK_AND_PLACE:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate target {target_name}"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Open gripper fully", {"target": 0.04}),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach above {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, f"Grasp pose at {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, "Close gripper", {"target": 0.0, "force": 15.0}),
            TaskDecomposition(TaskType.WAIT, "Settle grasp", {"duration": 0.3}),
            TaskDecomposition(TaskType.VERIFY_GRASP, "Verify object grasped"),
            TaskDecomposition(TaskType.MOVE_TO, "Lift target to transfer height"),
            TaskDecomposition(TaskType.MOVE_TO, "Transfer to dropoff location"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release object", {"target": 0.04}),
        ]
        bt = BTNode(
            "Sequence",
            f"pick_and_place_{target_name}",
            children=[
                BTNode("Action", f"Locate target {target_name}"),
                BTNode("Action", "Open gripper fully"),
                BTNode("Action", f"Approach above {target_name}"),
                BTNode("Action", f"Grasp pose at {target_name}"),
                BTNode("Action", "Close gripper"),
                BTNode("Condition", "Verify object grasped"),
                BTNode("Action", "Transfer to dropoff location"),
                BTNode("Action", "Release object"),
            ],
        )
        return IndustrialSkillTemplate(category, "Pick and Place", f"Pick up {target_name} and transfer", ["camera", "gripper"], tasks, bt)

    elif category == IndustrialSkillCategory.TIGHTEN_BOLT:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate bolt {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Align torque tool with bolt head"),
            TaskDecomposition(TaskType.MOVE_TO, "Engage bolt socket"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, "Actuate torque wrench", {"torque_limit_nm": 25.0}),
            TaskDecomposition(TaskType.WAIT, "Verify torque limit reached", {"duration": 0.5}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract torque tool"),
        ]
        bt = BTNode(
            "Sequence",
            f"tighten_bolt_{target_name}",
            children=[
                BTNode("Action", f"Locate bolt {target_name}"),
                BTNode("Action", "Align torque tool"),
                BTNode("Action", "Engage bolt socket"),
                BTNode("Action", "Actuate torque wrench to 25Nm"),
                BTNode("Condition", "Torque threshold verified"),
                BTNode("Action", "Retract tool"),
            ],
        )
        return IndustrialSkillTemplate(category, "Tighten Bolt", f"Torque tighten {target_name}", ["ft_sensor", "torque_tool"], tasks, bt)

    elif category == IndustrialSkillCategory.OPEN_DOOR:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, "Locate door handle"),
            TaskDecomposition(TaskType.MOVE_TO, "Approach door handle"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, "Grasp handle", {"force": 20.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Rotate handle downwards (30 deg)"),
            TaskDecomposition(TaskType.MOVE_TO, "Pull door open along circular arc"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release handle"),
        ]
        bt = BTNode(
            "Sequence",
            "open_door",
            children=[
                BTNode("Action", "Locate handle"),
                BTNode("Action", "Grasp handle"),
                BTNode("Action", "Rotate handle downwards"),
                BTNode("Action", "Pull door open along circular arc"),
                BTNode("Action", "Release handle"),
            ],
        )
        return IndustrialSkillTemplate(category, "Open Door", "Rotate latch and pull door open", ["camera", "ft_sensor"], tasks, bt)

    elif category == IndustrialSkillCategory.TOOL_EXCHANGE:
        tasks = [
            TaskDecomposition(TaskType.MOVE_TO, "Approach tool dock"),
            TaskDecomposition(TaskType.MOVE_TO, "Insert current tool into storage slot"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Unlock tool coupler"),
            TaskDecomposition(TaskType.MOVE_TO, "Retract to safe interchange height"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach new tool {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, "Lock tool coupler"),
            TaskDecomposition(TaskType.VERIFY_GRASP, "Verify tool coupler locked"),
        ]
        bt = BTNode(
            "Sequence",
            f"tool_exchange_{target_name}",
            children=[
                BTNode("Action", "Dock current tool"),
                BTNode("Action", "Unlock tool coupler"),
                BTNode("Action", f"Approach new tool {target_name}"),
                BTNode("Action", "Lock tool coupler"),
                BTNode("Condition", "Verify tool lock"),
            ],
        )
        return IndustrialSkillTemplate(category, "Tool Exchange", f"Exchange end-effector tool to {target_name}", ["coupler_sensor"], tasks, bt)

    elif category == IndustrialSkillCategory.INSPECT_SURFACE:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate inspection area on {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Move to initial inspection waypoint"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute coverage grid scanning path"),
            TaskDecomposition(TaskType.WAIT, "Capture high-res visual frame", {"duration": 0.2}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract inspection camera"),
        ]
        bt = BTNode(
            "Sequence",
            f"inspect_surface_{target_name}",
            children=[
                BTNode("Action", f"Locate area on {target_name}"),
                BTNode("Action", "Execute coverage grid scanning path"),
                BTNode("Action", "Capture visual inspection frames"),
            ],
        )
        return IndustrialSkillTemplate(category, "Inspect Surface", f"Visual surface inspection of {target_name}", ["camera_rgbd"], tasks, bt)

    elif category == IndustrialSkillCategory.WELD_SEAM:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate weld seam {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Approach seam start waypoint"),
            TaskDecomposition(TaskType.MOVE_TO, "Ignite torch & execute constant velocity seam trajectory"),
            TaskDecomposition(TaskType.WAIT, "Extinguish torch", {"duration": 0.1}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract welding torch"),
        ]
        bt = BTNode(
            "Sequence",
            f"weld_seam_{target_name}",
            children=[
                BTNode("Action", f"Locate weld seam {target_name}"),
                BTNode("Action", "Approach seam start"),
                BTNode("Action", "Execute arc weld seam trajectory"),
                BTNode("Action", "Extinguish torch & retract"),
            ],
        )
        return IndustrialSkillTemplate(category, "Weld Seam", f"Arc weld seam on {target_name}", ["torch_sensor", "seam_tracker"], tasks, bt)

    elif category == IndustrialSkillCategory.PALLETIZING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate pallet box {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach above {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp box {target_name}", {"force": 30.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Lift and move along collision-free pallet trajectory"),
            TaskDecomposition(TaskType.MOVE_TO, "Align with pallet matrix cell"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release box onto pallet stack"),
        ]
        bt = BTNode(
            "Sequence",
            f"palletize_{target_name}",
            children=[
                BTNode("Action", f"Locate box {target_name}"),
                BTNode("Action", "Grasp box"),
                BTNode("Action", "Transfer to pallet cell"),
                BTNode("Action", "Release onto pallet"),
            ],
        )
        return IndustrialSkillTemplate(category, "Palletizing", f"Palletize item {target_name}", ["camera", "lidar"], tasks, bt)

    elif category == IndustrialSkillCategory.POLISHING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Scan surface normal of {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach surface of {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute compliant impedance polishing raster pattern", {"force_nm": 10.0}),
            TaskDecomposition(TaskType.WAIT, "Verify polish finish quality", {"duration": 0.5}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract polishing tool"),
        ]
        bt = BTNode(
            "Sequence",
            f"polish_{target_name}",
            children=[
                BTNode("Action", "Scan surface"),
                BTNode("Action", "Compliant polishing raster"),
                BTNode("Condition", "Verify quality"),
            ],
        )
        return IndustrialSkillTemplate(category, "Surface Polishing", f"Impedance polish {target_name}", ["ft_sensor", "profilometer"], tasks, bt)

    elif category == IndustrialSkillCategory.DISASSEMBLY:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate fastener on {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Engage removal tool"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, "Extract fastener counter-clockwise"),
            TaskDecomposition(TaskType.MOVE_TO, "Separate component from assembly"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Place extracted component in sorting bin"),
        ]
        bt = BTNode(
            "Sequence",
            f"disassemble_{target_name}",
            children=[
                BTNode("Action", "Locate fastener"),
                BTNode("Action", "Extract fastener"),
                BTNode("Action", "Sort component"),
            ],
        )
        return IndustrialSkillTemplate(category, "Disassembly", f"Disassemble component {target_name}", ["camera", "ft_sensor"], tasks, bt)

    elif category == IndustrialSkillCategory.MOBILE_NAV:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate destination goal {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Plan dynamic SLAM navigation path"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute mobile base velocity commands along path"),
            TaskDecomposition(TaskType.WAIT, "Verify arrival at goal pose", {"tolerance_m": 0.05}),
        ]
        bt = BTNode(
            "Sequence",
            f"navigate_to_{target_name}",
            children=[
                BTNode("Action", "Plan SLAM path"),
                BTNode("Action", "Drive base to goal"),
                BTNode("Condition", "Verify arrival"),
            ],
        )
        return IndustrialSkillTemplate(category, "Mobile Navigation", f"Autonomous mobile navigation to {target_name}", ["lidar", "imu", "odom"], tasks, bt)

    elif category == IndustrialSkillCategory.PEGGING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate peg {target_name} and target hole"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach peg {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp peg {target_name}", {"force": 12.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Align peg axis with hole centerline"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute compliant insertion with search spiral", {"force_limit_n": 8.0}),
            TaskDecomposition(TaskType.WAIT, "Verify full insertion depth", {"duration": 0.3}),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release peg"),
        ]
        bt = BTNode(
            "Sequence",
            f"peg_insert_{target_name}",
            children=[
                BTNode("Action", "Locate peg and hole"),
                BTNode("Action", f"Grasp peg {target_name}"),
                BTNode("Action", "Align peg with hole"),
                BTNode("Action", "Compliant spiral insertion"),
                BTNode("Condition", "Verify insertion depth"),
                BTNode("Action", "Release peg"),
            ],
        )
        return IndustrialSkillTemplate(category, "Peg-in-Hole Insertion", f"Precision compliant insertion of {target_name}", ["ft_sensor", "camera"], tasks, bt)

    elif category == IndustrialSkillCategory.POURING_LIQUID:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate container {target_name} and receiving vessel"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach container {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp container {target_name}", {"force": 10.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Position container above receiving vessel"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute controlled tilt-pour trajectory", {"tilt_deg": 100.0}),
            TaskDecomposition(TaskType.WAIT, "Pour to target volume", {"duration": 2.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Return container to upright pose"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release container"),
        ]
        bt = BTNode(
            "Sequence",
            f"pour_{target_name}",
            children=[
                BTNode("Action", "Locate container and vessel"),
                BTNode("Action", f"Grasp container {target_name}"),
                BTNode("Action", "Position above receiving vessel"),
                BTNode("Action", "Controlled tilt-pour"),
                BTNode("Action", "Return to upright"),
                BTNode("Action", "Release container"),
            ],
        )
        return IndustrialSkillTemplate(category, "Liquid Pouring", f"Controlled tilt-pour from {target_name}", ["camera", "load_cell"], tasks, bt)

    elif category == IndustrialSkillCategory.PACKAGING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate item {target_name} and open carton"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp {target_name}", {"force": 15.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Transfer to packaging cavity"),
            TaskDecomposition(TaskType.MOVE_TO, "Lower item into cavity along guided path"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release item into package"),
            TaskDecomposition(TaskType.MOVE_TO, "Actuate carton flap closer"),
            TaskDecomposition(TaskType.WAIT, "Verify package sealed", {"duration": 0.3}),
        ]
        bt = BTNode(
            "Sequence",
            f"package_{target_name}",
            children=[
                BTNode("Action", f"Locate {target_name} and carton"),
                BTNode("Action", f"Grasp {target_name}"),
                BTNode("Action", "Lower into packaging cavity"),
                BTNode("Action", "Release into package"),
                BTNode("Action", "Close carton flap"),
                BTNode("Condition", "Verify package sealed"),
            ],
        )
        return IndustrialSkillTemplate(category, "Packaging", f"Pack {target_name} into shipping carton", ["camera", "gripper"], tasks, bt)

    elif category == IndustrialSkillCategory.CNC_LOADING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Locate workpiece {target_name} and CNC chuck"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach workpiece {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp workpiece {target_name}", {"force": 40.0}),
            TaskDecomposition(TaskType.WAIT, "Wait for CNC door open signal", {"duration": 0.5}),
            TaskDecomposition(TaskType.MOVE_TO, "Insert workpiece into CNC chuck"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release workpiece into chuck"),
            TaskDecomposition(TaskType.WAIT, "Wait for chuck clamp confirmation", {"duration": 0.5}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract arm clear of tool envelope"),
        ]
        bt = BTNode(
            "Sequence",
            f"cnc_load_{target_name}",
            children=[
                BTNode("Action", f"Locate workpiece {target_name} and chuck"),
                BTNode("Action", f"Grasp workpiece {target_name}"),
                BTNode("Condition", "CNC door open"),
                BTNode("Action", "Insert into chuck"),
                BTNode("Condition", "Chuck clamp confirmed"),
                BTNode("Action", "Retract clear of tool envelope"),
            ],
        )
        return IndustrialSkillTemplate(category, "CNC Machine Tending", f"Load {target_name} into CNC chuck", ["camera", "plc_io"], tasks, bt)

    elif category == IndustrialSkillCategory.SURGERY_ASSIST:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Track instrument {target_name} and surgical site"),
            TaskDecomposition(TaskType.MOVE_TO, f"Position instrument {target_name} at approach vector"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute tremor-filtered micro-positioning"),
            TaskDecomposition(TaskType.WAIT, "Hold steady for surgeon confirmation", {"duration": 1.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract instrument to safe standby pose"),
        ]
        bt = BTNode(
            "Sequence",
            f"surgery_assist_{target_name}",
            children=[
                BTNode("Action", f"Track instrument {target_name} and site"),
                BTNode("Action", "Position at approach vector"),
                BTNode("Action", "Tremor-filtered micro-positioning"),
                BTNode("Condition", "Hold for surgeon confirmation"),
                BTNode("Action", "Retract to standby"),
            ],
        )
        return IndustrialSkillTemplate(category, "Surgical Assistance", f"Tremor-filtered assistive positioning of {target_name}", ["stereo_camera", "ft_sensor"], tasks, bt)

    elif category == IndustrialSkillCategory.SORTING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Classify item {target_name} by visual features"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach {target_name}"),
            TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Grasp {target_name}", {"force": 12.0}),
            TaskDecomposition(TaskType.MOVE_TO, "Transfer to classified sorting bin"),
            TaskDecomposition(TaskType.OPEN_GRIPPER, "Release into sorting bin"),
        ]
        bt = BTNode(
            "Sequence",
            f"sort_{target_name}",
            children=[
                BTNode("Action", f"Classify {target_name}"),
                BTNode("Action", f"Grasp {target_name}"),
                BTNode("Action", "Transfer to sorting bin"),
                BTNode("Action", "Release into bin"),
            ],
        )
        return IndustrialSkillTemplate(category, "Sorting", f"Classify and sort {target_name} into correct bin", ["camera", "classifier"], tasks, bt)

    elif category == IndustrialSkillCategory.CLEANING:
        tasks = [
            TaskDecomposition(TaskType.PERCEIVE, f"Scan contamination map of {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, f"Approach surface of {target_name}"),
            TaskDecomposition(TaskType.MOVE_TO, "Execute compliant wiping raster pattern", {"force_n": 5.0}),
            TaskDecomposition(TaskType.WAIT, "Verify surface cleanliness", {"duration": 0.3}),
            TaskDecomposition(TaskType.MOVE_TO, "Retract cleaning tool"),
        ]
        bt = BTNode(
            "Sequence",
            f"clean_{target_name}",
            children=[
                BTNode("Action", "Scan contamination map"),
                BTNode("Action", "Approach surface"),
                BTNode("Action", "Compliant wiping raster"),
                BTNode("Condition", "Verify cleanliness"),
                BTNode("Action", "Retract tool"),
            ],
        )
        return IndustrialSkillTemplate(category, "Surface Cleaning", f"Compliant wipe-clean of {target_name}", ["ft_sensor", "camera"], tasks, bt)

    else:
        return _create_generic_custom_template(str(category), target_name)


def _create_generic_custom_template(skill_name: str, target_name: str) -> IndustrialSkillTemplate:
    """Create a generic fallback skill template for arbitrary open-world skills."""
    tasks = [
        TaskDecomposition(TaskType.PERCEIVE, f"Locate target {target_name} for {skill_name}"),
        TaskDecomposition(TaskType.MOVE_TO, f"Approach {target_name}"),
        TaskDecomposition(TaskType.CLOSE_GRIPPER, f"Engage {target_name}"),
        TaskDecomposition(TaskType.WAIT, "Execute primary skill action", {"duration": 0.5}),
        TaskDecomposition(TaskType.OPEN_GRIPPER, f"Disengage {target_name}"),
        TaskDecomposition(TaskType.MOVE_TO, "Retract to home posture"),
    ]
    bt = BTNode(
        "Sequence",
        f"{skill_name.lower()}_{target_name}",
        children=[
            BTNode("Action", f"Locate {target_name}"),
            BTNode("Action", f"Approach {target_name}"),
            BTNode("Action", f"Execute {skill_name}"),
            BTNode("Action", "Retract to home"),
        ],
    )
    return IndustrialSkillTemplate(
        category="CUSTOM_SKILL",
        name=f"Custom Skill: {skill_name}",
        description=f"Dynamically generated skill template for {skill_name} on {target_name}",
        required_sensors=["camera", "ft_sensor"],
        tasks=tasks,
        behavior_tree_root=bt,
    )
