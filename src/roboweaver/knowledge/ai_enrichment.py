"""
Knowledge Graph AI Enrichment — uses a local Ollama model to intelligently
suggest new edges, capability descriptions, and pairings for the knowledge graph.

This is a recommendation engine: it reads the existing graph and robot registry,
asks the LLM to reason about capabilities vs. skill requirements, and returns
structured suggestions that a human (or the dashboard UI) can review and apply.
Nothing is auto-applied — the graph is only mutated if the caller explicitly
merges the suggestions.

Capabilities:
  * suggest_edges() — Propose new SUITABLE_FOR edges by reasoning about robot
    capabilities vs. skill category requirements.
  * describe_robot() — Generate a rich semantic capability description for a
    robot from its spec.
  * suggest_pairings() — Recommend complementary robot pairs for multi-robot
    workcells.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.nlu.ollama_manager import OllamaManager, get_manager
from roboweaver.skills import IndustrialSkillCategory

if TYPE_CHECKING:
    from roboweaver.knowledge.graph import RoboticsKnowledgeGraph


@dataclass
class EdgeSuggestion:
    """A suggested SUITABLE_FOR edge between a robot and a skill category."""
    robot_id: str
    skill_category: str
    confidence: float
    reasoning: str


@dataclass
class RobotDescription:
    """AI-generated semantic description of a robot's capabilities."""
    robot_id: str
    summary: str
    strengths: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    ideal_tasks: list[str] = field(default_factory=list)


@dataclass
class RobotPairing:
    """A suggested complementary robot pairing for multi-robot workcells."""
    robot_a: str
    robot_b: str
    reasoning: str
    suggested_tasks: list[str] = field(default_factory=list)


@dataclass
class ObsidianSummary:
    """Suggested prose annotation for one graph node's Obsidian note."""
    node_id: str
    summary: str


@dataclass
class EnrichmentResult:
    """Full enrichment result. Individual lists may be empty if the LLM
    couldn't produce usable suggestions — `error` states why."""
    edge_suggestions: list[EdgeSuggestion] = field(default_factory=list)
    robot_descriptions: list[RobotDescription] = field(default_factory=list)
    robot_pairings: list[RobotPairing] = field(default_factory=list)
    obsidian_summaries: list[ObsidianSummary] = field(default_factory=list)
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


_ENRICHMENT_SYSTEM = """You are a robotics knowledge engineer. You analyze robot specifications \
and skill requirements to suggest capability relationships.

Rules:
- Only use robot IDs from the provided registry.
- Only use skill categories from the provided list.
- Base suggestions on real mechanical capabilities (DOF, payload, reach, gripper type).
- Confidence should be 0.0-1.0, based on how well the robot's specs match the skill's needs.
- Never suggest a capability the robot clearly cannot have (e.g., a mobile base doing welding).
- Output ONLY valid JSON, no prose.
"""

_SUGGEST_EDGES_TEMPLATE = """Analyze which robots are suitable for which skill categories \
based on their specifications.

**Available Robots:**
{robot_specs}

**Skill Categories:**
{skill_categories}

**Existing SUITABLE_FOR Edges:**
{existing_edges}

Suggest NEW edges that are missing. Output a JSON array:
[
  {{
    "robot_id": "<id from list>",
    "skill_category": "<category from list>",
    "confidence": 0.85,
    "reasoning": "<why this robot can perform this skill>"
  }}
]

Only suggest edges with confidence >= 0.5. Do not repeat existing edges."""

_DESCRIBE_ROBOT_TEMPLATE = """Generate a capability description for this robot.

**Robot:** {robot_id}
**Name:** {name}
**Manufacturer:** {manufacturer}
**DOF:** {dof}
**Payload:** {payload_kg}kg
**Reach:** {reach_m}m
**Gripper:** {gripper_type}
**Description:** {description}

Output JSON:
{{
  "summary": "<2-3 sentence capability summary>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "limitations": ["<limitation 1>", ...],
  "ideal_tasks": ["<task type 1>", "<task type 2>", ...]
}}"""

_SUGGEST_PAIRINGS_TEMPLATE = """Suggest complementary robot pairs for multi-robot workcells.

**Available Robots:**
{robot_specs}

Which robots work well together and why? Output a JSON array:
[
  {{
    "robot_a": "<id>",
    "robot_b": "<id>",
    "reasoning": "<why these complement each other>",
    "suggested_tasks": ["<task they could do together>"]
  }}
]

Focus on pairs where one robot's strengths compensate for the other's limitations."""

_SUMMARY_SYSTEM = """You write compact, factual Obsidian note summaries for a robotics knowledge graph.
Use only the supplied node properties and real graph relationships. Never invent capabilities or links.
Return one plain-text paragraph of at most 90 words."""

_SUMMARY_TEMPLATE = """Summarize this RoboWeaver knowledge graph node for an engineer.

Node id: {node_id}
Name: {name}
Type: {node_type}
Properties: {properties}
Outgoing relationships:
{relationships}

Explain what the node represents, its most important declared properties, and how its real links fit into the graph."""


class KnowledgeGraphEnricher:
    """Suggests knowledge graph enrichments using a local Ollama model."""

    def __init__(self, manager: OllamaManager | None = None):
        self.manager = manager or get_manager()

    def suggest_edges(
        self, existing_edges: list[tuple[str, str]] | None = None
    ) -> EnrichmentResult:
        """Suggest new SUITABLE_FOR edges based on robot specs vs. skill requirements."""
        robot_lines = []
        for rid, spec in sorted(ROBOT_REGISTRY.items()):
            robot_lines.append(
                f"  {rid}: {spec.name} | {spec.dof}-DOF | "
                f"{spec.payload_capacity_kg}kg | {spec.max_reach_m}m | "
                f"{spec.gripper_type} gripper | {spec.description[:80]}"
            )

        categories = sorted(c.value for c in IndustrialSkillCategory)

        existing = existing_edges or []
        existing_str = "\n".join(
            f"  {r} -> {s}" for r, s in existing
        ) or "  (none)"

        prompt = _SUGGEST_EDGES_TEMPLATE.format(
            robot_specs="\n".join(robot_lines),
            skill_categories=", ".join(categories),
            existing_edges=existing_str,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="enrichment",
            system=_ENRICHMENT_SYSTEM,
            json_mode=True,
            temperature=0.3,
            timeout=90.0,
        )

        if resp.text is None:
            return EnrichmentResult(error=resp.error, model=resp.model, latency_s=resp.latency_s)

        existing_set = set(existing)
        suggestions = [
            suggestion for suggestion in self._parse_edge_suggestions(resp.text)
            if (suggestion.robot_id, suggestion.skill_category) not in existing_set
        ]
        return EnrichmentResult(
            edge_suggestions=suggestions,
            model=resp.model,
            latency_s=resp.latency_s,
        )

    def describe_robot(self, robot_id: str) -> EnrichmentResult:
        """Generate a semantic capability description for a robot."""
        if robot_id not in ROBOT_REGISTRY:
            return EnrichmentResult(error=f"Unknown robot id '{robot_id}'")

        spec = ROBOT_REGISTRY[robot_id]
        prompt = _DESCRIBE_ROBOT_TEMPLATE.format(
            robot_id=robot_id,
            name=spec.name,
            manufacturer=spec.manufacturer,
            dof=spec.dof,
            payload_kg=spec.payload_capacity_kg,
            reach_m=spec.max_reach_m,
            gripper_type=spec.gripper_type,
            description=spec.description,
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="enrichment",
            system=_ENRICHMENT_SYSTEM,
            json_mode=True,
            temperature=0.3,
        )

        if resp.text is None:
            return EnrichmentResult(error=resp.error, model=resp.model, latency_s=resp.latency_s)

        desc = self._parse_robot_description(robot_id, resp.text)
        return EnrichmentResult(
            robot_descriptions=[desc] if desc else [],
            model=resp.model,
            latency_s=resp.latency_s,
        )

    def suggest_pairings(self) -> EnrichmentResult:
        """Suggest complementary robot pairs for multi-robot workcells."""
        robot_lines = []
        for rid, spec in sorted(ROBOT_REGISTRY.items()):
            robot_lines.append(
                f"  {rid}: {spec.name} ({spec.dof}-DOF, "
                f"{spec.gripper_type}, {spec.payload_capacity_kg}kg, {spec.max_reach_m}m)"
            )

        prompt = _SUGGEST_PAIRINGS_TEMPLATE.format(
            robot_specs="\n".join(robot_lines),
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="enrichment",
            system=_ENRICHMENT_SYSTEM,
            json_mode=True,
            temperature=0.4,
        )

        if resp.text is None:
            return EnrichmentResult(error=resp.error, model=resp.model, latency_s=resp.latency_s)

        pairings = self._parse_pairings(resp.text)
        return EnrichmentResult(
            robot_pairings=pairings,
            model=resp.model,
            latency_s=resp.latency_s,
        )

    def summarize_obsidian_node(
        self, graph: "RoboticsKnowledgeGraph", node_id: str,
    ) -> EnrichmentResult:
        """Generate an optional annotation for one real Obsidian graph note."""
        node = graph.get_node(node_id)
        if node is None:
            return EnrichmentResult(error=f"Unknown knowledge graph node '{node_id}'")
        relationships = []
        for edge in graph.edges:
            if edge.source_id != node_id:
                continue
            target = graph.get_node(edge.target_id)
            relationships.append(
                f"- {edge.relation.value} -> {target.name if target else edge.target_id}"
            )
        prompt = _SUMMARY_TEMPLATE.format(
            node_id=node.id,
            name=node.name,
            node_type=node.type.value,
            properties=json.dumps(node.properties, sort_keys=True, default=str),
            relationships="\n".join(relationships) or "- none",
        )
        resp = self.manager.generate(
            prompt=prompt,
            feature="enrichment",
            system=_SUMMARY_SYSTEM,
            temperature=0.2,
        )
        if resp.text is None:
            return EnrichmentResult(error=resp.error, model=resp.model, latency_s=resp.latency_s)
        summary = " ".join(resp.text.strip().split())[:800]
        return EnrichmentResult(
            obsidian_summaries=[ObsidianSummary(node_id=node_id, summary=summary)],
            model=resp.model,
            latency_s=resp.latency_s,
        )

    # ── Parsers ───────────────────────────────────────────────────────

    def _parse_edge_suggestions(self, raw: str) -> list[EdgeSuggestion]:
        items = _parse_json_array(raw)
        valid_robots = set(ROBOT_REGISTRY.keys())
        valid_categories = {c.value for c in IndustrialSkillCategory}

        suggestions = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("robot_id", ""))
            cat = str(item.get("skill_category", ""))
            if rid not in valid_robots or cat not in valid_categories:
                continue
            try:
                conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            except (TypeError, ValueError):
                conf = 0.5
            if conf < 0.5:
                continue
            suggestions.append(EdgeSuggestion(
                robot_id=rid,
                skill_category=cat,
                confidence=conf,
                reasoning=str(item.get("reasoning", ""))[:300],
            ))
        return suggestions

    def _parse_robot_description(self, robot_id: str, raw: str) -> RobotDescription | None:
        parsed = _parse_json_object(raw)
        if not isinstance(parsed, dict):
            return None
        return RobotDescription(
            robot_id=robot_id,
            summary=str(parsed.get("summary", ""))[:500],
            strengths=[str(s) for s in parsed.get("strengths", []) if isinstance(s, str)][:6],
            limitations=[str(s) for s in parsed.get("limitations", []) if isinstance(s, str)][:6],
            ideal_tasks=[str(s) for s in parsed.get("ideal_tasks", []) if isinstance(s, str)][:8],
        )

    def _parse_pairings(self, raw: str) -> list[RobotPairing]:
        items = _parse_json_array(raw)
        valid_robots = set(ROBOT_REGISTRY.keys())

        pairings = []
        for item in items:
            if not isinstance(item, dict):
                continue
            a = str(item.get("robot_a", ""))
            b = str(item.get("robot_b", ""))
            if a not in valid_robots or b not in valid_robots or a == b:
                continue
            pairings.append(RobotPairing(
                robot_a=a,
                robot_b=b,
                reasoning=str(item.get("reasoning", ""))[:300],
                suggested_tasks=[str(t) for t in item.get("suggested_tasks", []) if isinstance(t, str)][:5],
            ))
        return pairings


def _parse_json_array(raw: str) -> list[Any]:
    """Robustly extract a JSON array from model output."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # Some models wrap arrays in an object
            for key in ("suggestions", "edges", "pairings", "steps", "results"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
        return []
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return []


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Extract a JSON object even when a small model wraps it in prose/fences."""
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        return None
