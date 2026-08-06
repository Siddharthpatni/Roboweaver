"""Hermetic tests for Ollama-backed knowledge graph suggestions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from roboweaver.knowledge.ai_enrichment import KnowledgeGraphEnricher
from roboweaver.knowledge.ingest_registry import build_graph_from_registry
from roboweaver.nlu.ollama_manager import OllamaManager, OllamaResponse


def _manager(text: str | None, error: str | None = None) -> OllamaManager:
    manager = MagicMock(spec=OllamaManager)
    manager.generate.return_value = OllamaResponse(
        text=text, error=error, model="llama3.1:8b", latency_s=0.25,
    )
    return manager


def test_edge_suggestions_are_validated_against_real_taxonomies():
    payload = json.dumps([
        {
            "robot_id": "franka_panda",
            "skill_category": "PICK_AND_PLACE",
            "confidence": 0.91,
            "reasoning": "Declared gripper and suitable reach.",
        },
        {
            "robot_id": "invented_robot",
            "skill_category": "TELEPORTATION",
            "confidence": 0.99,
            "reasoning": "hallucinated",
        },
    ])
    result = KnowledgeGraphEnricher(_manager(payload)).suggest_edges()
    assert len(result.edge_suggestions) == 1
    assert result.edge_suggestions[0].robot_id == "franka_panda"
    assert result.error is None


def test_robot_description_recovers_fenced_json():
    payload = """```json
    {"summary":"Precise arm.","strengths":["dexterity"],"limitations":["payload"],"ideal_tasks":["assembly"]}
    ```"""
    result = KnowledgeGraphEnricher(_manager(payload)).describe_robot("franka_panda")
    assert result.robot_descriptions[0].summary == "Precise arm."
    assert result.robot_descriptions[0].strengths == ["dexterity"]


def test_obsidian_summary_uses_a_real_graph_node_and_fails_honestly():
    graph = build_graph_from_registry()
    enricher = KnowledgeGraphEnricher(_manager("A factual compact summary."))
    result = enricher.summarize_obsidian_node(graph, "robot_franka_panda")
    assert result.obsidian_summaries[0].node_id == "robot_franka_panda"
    prompt = enricher.manager.generate.call_args.kwargs["prompt"]
    assert "Franka" in prompt

    missing = enricher.summarize_obsidian_node(graph, "not_a_real_node")
    assert missing.obsidian_summaries == []
    assert "Unknown" in missing.error


def test_offline_enrichment_returns_stated_error():
    result = KnowledgeGraphEnricher(_manager(None, "Ollama unreachable")).suggest_pairings()
    assert result.robot_pairings == []
    assert result.error == "Ollama unreachable"
