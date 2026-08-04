"""
Real knowledge graph ingestion (gap-fix batch, item 2) -- replaces the ~13
hand-seeded demo nodes (knowledge/graph.py::create_default_robotics_knowledge_graph)
with real nodes/edges built from the actual, live registries: ROBOT_REGISTRY,
RoboticsPackageNexus.PACKAGE_CATALOG, and every NL-reachable IndustrialSkillCategory.
Every edge here is traceable to a real field on real data, not invented.
"""

from __future__ import annotations

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.knowledge.graph import RoboticsKnowledgeGraph
from roboweaver.knowledge.ontology import KnowledgeEdge, KnowledgeNode, NodeType, RelationType
from roboweaver.knowledge.package_nexus import RoboticsPackageNexus
from roboweaver.skills.taxonomy import IndustrialSkillCategory, get_industrial_skill_template

# Mirrors compiler.py::ACTION_CATEGORY_MAP's real, reachable categories (17, after
# the gap-fix batch's item 1b added the last 4). CUSTOM_SKILL is deliberately
# excluded -- it's a generic fallback, not a real distinct skill.
_REACHABLE_CATEGORIES = [c for c in IndustrialSkillCategory if c is not IndustrialSkillCategory.CUSTOM_SKILL]

_FORCE_TORQUE_SENSOR_NAMES = {"ft_sensor", "force_torque"}


def build_graph_from_registry() -> RoboticsKnowledgeGraph:
    """Real ingestion: one ROBOT node per distinct RobotSpec, one PACKAGE node per
    catalog entry (with real COMPATIBLE_WITH edges to the robots its own
    compatible_robots list names), one SKILL node per reachable category (with a
    SUITABLE_FOR edge to a robot when the skill's real required_sensors are
    satisfiable -- force/torque is the only sensor RobotSpec actually declares, so
    that's the only real per-robot gate available; skills with no force/torque
    requirement connect to every robot, since nothing else in RobotSpec constrains
    them)."""
    graph = RoboticsKnowledgeGraph()

    robots_by_id = {}
    for spec in ROBOT_REGISTRY.values():
        if spec.id in robots_by_id:
            continue
        robots_by_id[spec.id] = spec
        graph.add_node(
            KnowledgeNode(
                id=f"robot_{spec.id}",
                name=spec.name,
                type=NodeType.ROBOT,
                properties={
                    "dof": spec.dof,
                    "payload_capacity_kg": spec.payload_capacity_kg,
                    "max_reach_m": spec.max_reach_m,
                    "has_force_torque_sensor": spec.has_force_torque_sensor,
                    "manufacturer": spec.manufacturer,
                },
            )
        )

    for pkg in RoboticsPackageNexus.PACKAGE_CATALOG.values():
        graph.add_node(
            KnowledgeNode(
                id=f"package_{pkg.id}",
                name=pkg.name,
                type=NodeType.PACKAGE,
                properties={"category": pkg.category, "description": pkg.description, "version": pkg.version},
            )
        )
        for robot_id in pkg.compatible_robots:
            robot_node_id = f"robot_{robot_id}"
            if robot_node_id in graph.nodes:
                graph.add_edge(
                    KnowledgeEdge(
                        source_id=f"package_{pkg.id}", target_id=robot_node_id,
                        relation=RelationType.COMPATIBLE_WITH,
                    )
                )

    for category in _REACHABLE_CATEGORIES:
        template = get_industrial_skill_template(category)
        skill_node_id = f"skill_{category.value.lower()}"
        graph.add_node(
            KnowledgeNode(
                id=skill_node_id,
                name=template.name,
                type=NodeType.SKILL,
                properties={
                    "category": category.value,
                    "description": template.description,
                    "required_sensors": template.required_sensors,
                },
            )
        )
        needs_force_torque = bool(_FORCE_TORQUE_SENSOR_NAMES & set(template.required_sensors))
        for robot_id, spec in robots_by_id.items():
            if needs_force_torque and not spec.has_force_torque_sensor:
                continue
            graph.add_edge(
                KnowledgeEdge(
                    source_id=skill_node_id, target_id=f"robot_{robot_id}",
                    relation=RelationType.SUITABLE_FOR,
                )
            )

    return graph
