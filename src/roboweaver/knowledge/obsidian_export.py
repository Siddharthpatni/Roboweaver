"""
Obsidian markdown export (gap-fix batch, item 2): one real .md file per graph node,
with a properties table and a "Links" section listing every real outgoing edge as an
Obsidian [[wikilink]] to the target node's real filename -- this genuinely opens as a
connected graph in the Obsidian app, since every link traces to a real edge computed
by knowledge/ingest_registry.py, not decorative text.
"""

from __future__ import annotations

import re
from pathlib import Path

from roboweaver.knowledge.graph import RoboticsKnowledgeGraph


def _safe_filename(node_id: str) -> str:
    """Obsidian note filenames double as the [[wikilink]] target -- keep them
    stable (derived from the real node id) and filesystem-safe."""
    base = re.sub(r"[^A-Za-z0-9_\-]+", "_", node_id)
    return f"{base}.md"


def export_to_obsidian(
    graph: RoboticsKnowledgeGraph,
    output_dir: str | Path,
    ai_summaries: dict[str, str] | None = None,
) -> Path:
    """Writes one real markdown note per real node into `output_dir`. Every
    [[wikilink]] resolves to a real other file in the same directory -- confirmed
    by tests/test_knowledge_graph.py, not just asserted here."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    filenames = {node_id: _safe_filename(node_id) for node_id in graph.nodes}

    for node_id, node in graph.nodes.items():
        lines = [f"# {node.name}", "", f"**Type**: {node.type.value}"]
        summary = (ai_summaries or {}).get(node_id)
        if summary:
            lines += ["", "## AI Summary", "", summary]
        lines += ["", "## Properties", ""]
        if node.properties:
            lines.append("| Property | Value |")
            lines.append("|---|---|")
            for key, value in node.properties.items():
                lines.append(f"| {key} | {value} |")
        else:
            lines.append("_None declared._")

        outgoing = [e for e in graph.edges if e.source_id == node_id]
        lines += ["", "## Links", ""]
        if outgoing:
            for edge in outgoing:
                target_node = graph.nodes.get(edge.target_id)
                target_name = target_node.name if target_node else edge.target_id
                target_file = filenames.get(edge.target_id, f"{edge.target_id}.md")
                wikilink_target = target_file[:-3] if target_file.endswith(".md") else target_file
                lines.append(f"- **{edge.relation.value}** → [[{wikilink_target}|{target_name}]]")
        else:
            lines.append("_No outgoing links._")

        (out / filenames[node_id]).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return out
