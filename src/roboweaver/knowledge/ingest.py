"""
Knowledge Ingestor — extracts robotics entities and constraints from text or documentation.
"""

from __future__ import annotations

import re
from roboweaver.knowledge.graph import RoboticsKnowledgeGraph
from roboweaver.knowledge.ontology import KnowledgeNode, NodeType


class KnowledgeIngestor:
    """Extracts skills, tools, objects, and constraints from robotics documentation."""

    def __init__(self, kg: RoboticsKnowledgeGraph | None = None):
        if kg is None:
            self.kg = RoboticsKnowledgeGraph()
        else:
            self.kg = kg

    def ingest_text(self, text: str) -> RoboticsKnowledgeGraph:
        """Parse unstructured text and build knowledge graph entries."""
        lines = text.splitlines()

        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            # Skill detection
            skill_match = re.search(r"Skill:\s*([A-Za-z0-9_\s]+)", line_clean, re.IGNORECASE)
            if skill_match:
                name = skill_match.group(1).strip()
                node_id = f"skill_{name.lower().replace(' ', '_')}"
                self.kg.add_node(KnowledgeNode(node_id, name, NodeType.SKILL))

            # Tool detection
            tool_match = re.search(r"Tool:\s*([A-Za-z0-9_\s]+)", line_clean, re.IGNORECASE)
            if tool_match:
                name = tool_match.group(1).strip()
                node_id = f"tool_{name.lower().replace(' ', '_')}"
                self.kg.add_node(KnowledgeNode(node_id, name, NodeType.TOOL))

            # Object detection
            obj_match = re.search(r"Object:\s*([A-Za-z0-9_\s]+)", line_clean, re.IGNORECASE)
            if obj_match:
                name = obj_match.group(1).strip()
                node_id = f"obj_{name.lower().replace(' ', '_')}"
                self.kg.add_node(KnowledgeNode(node_id, name, NodeType.OBJECT))

        return self.kg
