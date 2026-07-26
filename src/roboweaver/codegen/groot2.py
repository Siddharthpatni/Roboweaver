"""
Groot2 / BehaviorTree.CPP v4 XML Generator — exports compiled skills to Groot2 format.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from roboweaver.types import BTNode, CompiledSkill


def export_groot2_xml(skill: CompiledSkill) -> str:
    """Export a CompiledSkill to Groot2 / BehaviorTree.CPP v4 XML string."""
    root_elem = ET.Element("root", {"BTCPP_format": "4"})
    tree_id = f"{skill.intent.action.value.lower()}_{skill.intent.object_name}_tree"
    bt_elem = ET.SubElement(root_elem, "BehaviorTree", {"ID": tree_id})

    def _convert_node(parent_xml: ET.Element, bt_node: BTNode) -> None:
        tag = bt_node.type
        if tag not in ["Sequence", "Fallback", "Action", "Condition", "Decorator"]:
            tag = "Action"

        elem_attrs = {"name": bt_node.name}
        node_elem = ET.SubElement(parent_xml, tag, elem_attrs)

        for child in bt_node.children:
            _convert_node(node_elem, child)

    _convert_node(bt_elem, skill.behavior_tree)

    # Format pretty XML
    raw_str = ET.tostring(root_elem, encoding="utf-8")
    parsed = minidom.parseString(raw_str)
    return parsed.toprettyxml(indent="  ")
