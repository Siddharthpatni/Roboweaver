"""
Verification suite for real knowledge graph ingestion, multi-hop path, and Obsidian
export -- gap-fix batch, item 2.
"""

import tempfile
from pathlib import Path

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.knowledge.ingest_registry import build_graph_from_registry
from roboweaver.knowledge.obsidian_export import export_to_obsidian
from roboweaver.knowledge.ontology import NodeType
from roboweaver.knowledge.package_nexus import RoboticsPackageNexus


def test_ingestion_produces_real_counts_matching_live_registries():
    print("\n[TEST 1] Testing build_graph_from_registry() produces real node counts matching live data...")
    graph = build_graph_from_registry()

    distinct_robot_ids = {spec.id for spec in ROBOT_REGISTRY.values()}
    assert len(graph.find_nodes_by_type(NodeType.ROBOT)) == len(distinct_robot_ids)
    assert len(graph.find_nodes_by_type(NodeType.PACKAGE)) == len(RoboticsPackageNexus.PACKAGE_CATALOG)
    assert len(graph.find_nodes_by_type(NodeType.SKILL)) == 17  # every reachable category, incl. the 4 gap-fixed ones
    assert len(graph.edges) > 0
    print(f"  -> {len(distinct_robot_ids)} real robots, {len(RoboticsPackageNexus.PACKAGE_CATALOG)} "
          f"real packages, 17 real skills, {len(graph.edges)} real edges [PASSED]")


def test_package_compatible_with_edges_match_real_data():
    print("\n[TEST 2] Testing PACKAGE->ROBOT edges match the package's real compatible_robots list...")
    graph = build_graph_from_registry()
    nav2 = RoboticsPackageNexus.PACKAGE_CATALOG["nav2_bringup"]
    real_targets = {
        e.target_id for e in graph.edges if e.source_id == "package_nav2_bringup"
    }
    expected_targets = {f"robot_{rid}" for rid in nav2.compatible_robots if f"robot_{rid}" in graph.nodes}
    assert real_targets == expected_targets
    print(f"  -> nav2_bringup's real edges exactly match its declared compatible_robots [PASSED]")


def test_force_torque_skill_only_connects_to_robots_that_declare_the_sensor():
    print("\n[TEST 3] Testing a force/torque-requiring skill only connects to robots that really have the sensor...")
    graph = build_graph_from_registry()
    tighten_targets = {e.target_id for e in graph.edges if e.source_id == "skill_tighten_bolt"}
    for target_id in tighten_targets:
        robot_node = graph.nodes[target_id]
        assert robot_node.properties["has_force_torque_sensor"] is True
    # temi has no force/torque sensor -- must NOT be connected.
    assert "robot_temi" not in tighten_targets
    print(f"  -> TIGHTEN_BOLT connects only to real force/torque-capable robots [PASSED]")


def test_find_path_returns_a_real_multi_hop_path():
    print("\n[TEST 4] Testing find_path() returns a real, edge-backed multi-hop path...")
    graph = build_graph_from_registry()
    path = graph.find_path("skill_tighten_bolt", "package_nav2_bringup", max_hops=6)
    assert path is not None
    assert path[0] == "skill_tighten_bolt"
    assert path[-1] == "package_nav2_bringup"
    # Every consecutive pair in the path must be a real edge (in either direction,
    # since find_path treats the graph as undirected).
    edge_pairs = {(e.source_id, e.target_id) for e in graph.edges} | {
        (e.target_id, e.source_id) for e in graph.edges
    }
    for a, b in zip(path, path[1:]):
        assert (a, b) in edge_pairs, f"{a} -> {b} is not a real edge"
    print(f"  -> real path: {' -> '.join(path)} [PASSED]")


def test_find_path_returns_none_when_unreachable():
    print("\n[TEST 5] Testing find_path() returns None (not a fabricated path) when nodes don't exist/aren't connected...")
    graph = build_graph_from_registry()
    assert graph.find_path("nonexistent_a", "nonexistent_b") is None
    print("  -> None returned honestly for unknown node ids [PASSED]")


def test_obsidian_export_produces_real_cross_linked_notes():
    print("\n[TEST 6] Testing export_to_obsidian() produces real .md files whose [[links]] resolve...")
    graph = build_graph_from_registry()
    with tempfile.TemporaryDirectory() as tmpdir:
        out = export_to_obsidian(graph, tmpdir)
        files = {p.name for p in Path(out).glob("*.md")}
        assert len(files) == len(graph.nodes)

        content = (Path(out) / "skill_tighten_bolt.md").read_text()
        assert "# Tighten Bolt" in content
        assert "[[robot_franka_panda|" in content

        # Every [[wikilink|...]] target in every file must resolve to a real file
        # in this same directory.
        import re
        link_pattern = re.compile(r"\[\[([^\|\]]+)\|")
        for md_file in Path(out).glob("*.md"):
            for match in link_pattern.finditer(md_file.read_text()):
                target = match.group(1)
                assert f"{target}.md" in files, f"{md_file.name} links to missing file {target}.md"
    print(f"  -> {len(files)} real notes, every [[wikilink]] resolves to a real file [PASSED]")


if __name__ == "__main__":
    print("=== STARTING KNOWLEDGE GRAPH + OBSIDIAN EXPORT (GAP-FIX ITEM 2) VERIFICATION ===")
    test_ingestion_produces_real_counts_matching_live_registries()
    test_package_compatible_with_edges_match_real_data()
    test_force_torque_skill_only_connects_to_robots_that_declare_the_sensor()
    test_find_path_returns_a_real_multi_hop_path()
    test_find_path_returns_none_when_unreachable()
    test_obsidian_export_produces_real_cross_linked_notes()
    print("\n=== ALL KNOWLEDGE GRAPH TESTS PASSED SUCCESSFULLY ===")
