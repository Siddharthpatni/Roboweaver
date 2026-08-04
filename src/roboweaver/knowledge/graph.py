"""
Robotics Knowledge Graph Engine — represents, queries, and serializes robotics knowledge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roboweaver.knowledge.ontology import KnowledgeEdge, KnowledgeNode, NodeType, RelationType


class RoboticsKnowledgeGraph:
    """In-memory and persistent Robotics Knowledge Graph."""

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KnowledgeEdge] = []

    def add_node(self, node: KnowledgeNode) -> None:
        """Add or update a knowledge node."""
        self.nodes[node.id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        """Add a directed edge between nodes."""
        if edge.source_id not in self.nodes:
            raise KeyError(f"Source node ID '{edge.source_id}' not in graph.")
        if edge.target_id not in self.nodes:
            raise KeyError(f"Target node ID '{edge.target_id}' not in graph.")
        self.edges.append(edge)

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        return self.nodes.get(node_id)

    def find_nodes_by_type(self, node_type: NodeType) -> list[KnowledgeNode]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def get_related_nodes(
        self, node_id: str, relation: RelationType | None = None
    ) -> list[KnowledgeNode]:
        """Find all target nodes connected to node_id."""
        targets = []
        for edge in self.edges:
            if edge.source_id == node_id:
                if relation is None or edge.relation == relation:
                    node = self.nodes.get(edge.target_id)
                    if node is not None:
                        targets.append(node)
        return targets

    def find_path(self, start_id: str, end_id: str, max_hops: int = 6) -> list[str] | None:
        """Real multi-hop BFS over self.edges (undirected -- edges here mostly
        represent structural relationships like COMPATIBLE_WITH/REQUIRES_TOOL where
        traversing "backwards" is still a meaningful path, e.g. "which skill leads
        to this package"). Returns the first-found shortest path of node ids
        (inclusive of start/end), or None if unreachable within max_hops."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return None
        if start_id == end_id:
            return [start_id]

        adjacency: dict[str, set[str]] = {node_id: set() for node_id in self.nodes}
        for edge in self.edges:
            if edge.source_id in adjacency and edge.target_id in adjacency:
                adjacency[edge.source_id].add(edge.target_id)
                adjacency[edge.target_id].add(edge.source_id)

        visited = {start_id}
        frontier = [[start_id]]
        hops = 0
        while frontier and hops < max_hops:
            next_frontier: list[list[str]] = []
            for path in frontier:
                current = path[-1]
                for neighbor in adjacency.get(current, ()):
                    if neighbor == end_id:
                        return path + [neighbor]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(path + [neighbor])
            frontier = next_frontier
            hops += 1
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to primitive dictionary."""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type.value,
                    "properties": n.properties,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "relation": e.relation.value,
                    "properties": e.properties,
                }
                for e in self.edges
            ],
        }

    def save(self, path: str | Path) -> None:
        """Save knowledge graph to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> RoboticsKnowledgeGraph:
        """Load knowledge graph from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        kg = cls()
        for nd in data.get("nodes", []):
            kg.add_node(
                KnowledgeNode(
                    id=nd["id"],
                    name=nd["name"],
                    type=NodeType(nd["type"]),
                    properties=nd.get("properties", {}),
                )
            )

        for ed in data.get("edges", []):
            kg.add_edge(
                KnowledgeEdge(
                    source_id=ed["source_id"],
                    target_id=ed["target_id"],
                    relation=RelationType(ed["relation"]),
                    properties=ed.get("properties", {}),
                )
            )

        return kg


def create_default_robotics_knowledge_graph() -> RoboticsKnowledgeGraph:
    """Create a rich pre-seeded robotics knowledge graph."""
    kg = RoboticsKnowledgeGraph()

    # Skills
    kg.add_node(KnowledgeNode("skill_pick", "Pick and Place", NodeType.SKILL, {"difficulty": "basic"}))
    kg.add_node(KnowledgeNode("skill_tighten", "Tighten Bolt", NodeType.SKILL, {"difficulty": "intermediate"}))
    kg.add_node(KnowledgeNode("skill_open", "Open Door", NodeType.SKILL, {"difficulty": "intermediate"}))
    kg.add_node(KnowledgeNode("skill_push", "Push Object", NodeType.SKILL, {"difficulty": "basic"}))

    # Tools
    kg.add_node(KnowledgeNode("tool_gripper", "Parallel Jaw Gripper", NodeType.TOOL, {"max_payload": 2.0}))
    kg.add_node(KnowledgeNode("tool_wrench", "Torque Wrench", NodeType.TOOL, {"max_torque": 50.0}))

    # Objects
    kg.add_node(KnowledgeNode("obj_cube", "Red Cube", NodeType.OBJECT, {"dimensions": [0.04, 0.04, 0.04]}))
    kg.add_node(KnowledgeNode("obj_bolt", "M8 Hex Bolt", NodeType.OBJECT, {"thread_pitch": 1.25}))

    # Constraints
    kg.add_node(KnowledgeNode("c_torque", "Max Torque Limit", NodeType.CONSTRAINT, {"value": 25.0, "unit": "Nm"}))
    kg.add_node(KnowledgeNode("c_speed", "Velocity Margin", NodeType.CONSTRAINT, {"value": 1.5, "unit": "rad/s"}))

    # Edges
    kg.add_edge(KnowledgeEdge("skill_pick", "tool_gripper", RelationType.REQUIRES_TOOL))
    kg.add_edge(KnowledgeEdge("skill_pick", "obj_cube", RelationType.TARGETS_OBJECT))
    kg.add_edge(KnowledgeEdge("skill_tighten", "tool_wrench", RelationType.REQUIRES_TOOL))
    kg.add_edge(KnowledgeEdge("skill_tighten", "obj_bolt", RelationType.TARGETS_OBJECT))
    kg.add_edge(KnowledgeEdge("skill_tighten", "c_torque", RelationType.HAS_CONSTRAINT))

    return kg
