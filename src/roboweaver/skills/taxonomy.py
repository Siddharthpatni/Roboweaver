"""
Universal Industrial Skill Taxonomy & Template Decomposers.

Supports 6 major industrial robot capability templates:
- PICK_AND_PLACE
- TIGHTEN_BOLT
- OPEN_DOOR
- TOOL_EXCHANGE
- INSPECT_SURFACE
- WELD_SEAM
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from roboweaver.types import Action, TaskDecomposition, TaskType, BTNode


class IndustrialSkillCategory(Enum):
    PICK_AND_PLACE = "PICK_AND_PLACE"
    TIGHTEN_BOLT = "TIGHTEN_BOLT"
    OPEN_DOOR = "OPEN_DOOR"
    TOOL_EXCHANGE = "TOOL_EXCHANGE"
    INSPECT_SURFACE = "INSPECT_SURFACE"
    WELD_SEAM = "WELD_SEAM"


@dataclass
class IndustrialSkillTemplate:
    category: IndustrialSkillCategory
    name: str
    description: str
    required_sensors: list[str]
    tasks: list[TaskDecomposition]
    behavior_tree_root: BTNode


def get_industrial_skill_template(
    category: IndustrialSkillCategory, target_name: str = "object"
) -> IndustrialSkillTemplate:
    """Retrieve structured task graph and BT for industrial skill category."""

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

    else:  # WELD_SEAM
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
