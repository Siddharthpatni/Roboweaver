"""
Groot2 / BehaviorTree.CPP v4 XML Generator — exports compiled skills to Groot2 format.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from roboweaver.identifiers import safe_identifier
from roboweaver.ir.schema import IRBehaviorNode, RoboIR
from roboweaver.types import BTNode, CompiledSkill


def _export_behavior_tree(action: str, object_name: str, behavior_tree: BTNode | IRBehaviorNode) -> str:
    root_elem = ET.Element("root", {"BTCPP_format": "4"})
    tree_id = safe_identifier(f"{action}_{object_name}_tree", default="skill_tree")
    bt_elem = ET.SubElement(root_elem, "BehaviorTree", {"ID": tree_id})

    def _convert_node(parent_xml: ET.Element, bt_node: BTNode | IRBehaviorNode) -> None:
        tag = bt_node.type
        if tag not in ["Sequence", "Fallback", "Action", "Condition", "Decorator"]:
            tag = "Action"
        node_elem = ET.SubElement(parent_xml, tag, {"name": bt_node.name})
        for child in bt_node.children:
            _convert_node(node_elem, child)

    _convert_node(bt_elem, behavior_tree)
    ET.indent(root_elem, space="  ")
    return ET.tostring(root_elem, encoding="unicode", xml_declaration=True) + "\n"


def export_groot2_xml(skill: CompiledSkill) -> str:
    """Export a CompiledSkill to Groot2 / BehaviorTree.CPP v4 XML string."""
    return _export_behavior_tree(
        skill.intent.action.value,
        skill.intent.object_name,
        skill.behavior_tree,
    )


def export_groot2_ir(ir: RoboIR) -> str:
    """Export behavior exclusively from a complete RoboIR program."""
    if ir.program is None:
        raise ValueError("RoboIR has no complete program; behavior export is impossible")
    return _export_behavior_tree(ir.action, ir.program.object_name, ir.program.behavior_tree)
