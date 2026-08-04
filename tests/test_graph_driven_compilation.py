"""
Verification suite for the knowledge graph actually influencing a compiler
decision, not just documenting robot/package/skill relationships:
SkillCompiler.classify_category() (a real, public, robot-independent
classification entry point) feeds knowledge/ingest_registry.py's
suggest_robots_for_instruction(), which optimize/cost_model.py::compare_robots()
now calls when robot_ids is omitted.
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.knowledge.ingest_registry import build_graph_from_registry, suggest_robots_for_instruction
from roboweaver.skills.taxonomy import IndustrialSkillCategory


def test_classify_category_matches_the_real_action_category_map():
    print("\n[TEST 1] Testing SkillCompiler.classify_category() matches real ACTION_CATEGORY_MAP routing...")
    from roboweaver.compiler import ACTION_CATEGORY_MAP

    compiler = SkillCompiler(target_robot="franka_panda")
    tighten_intent = compiler._parse_intent("Tighten the M8 bolt")
    assert compiler.classify_category("Tighten the M8 bolt") == ACTION_CATEGORY_MAP[tighten_intent.action]
    assert compiler.classify_category("Tighten the M8 bolt") == IndustrialSkillCategory.TIGHTEN_BOLT
    print("  -> real classification matches the same ACTION_CATEGORY_MAP compile() itself routes through [PASSED]")


def test_classify_category_is_robot_independent():
    print("\n[TEST 2] Testing classify_category() gives the same real answer regardless of target robot...")
    a = SkillCompiler(target_robot="franka_panda").classify_category("Weld the seam")
    b = SkillCompiler(target_robot="temi").classify_category("Weld the seam")
    assert a == b == IndustrialSkillCategory.WELD_SEAM
    print("  -> classification is a pure function of the instruction, not the robot [PASSED]")


def test_suggest_robots_for_instruction_matches_the_real_graph_edges():
    print("\n[TEST 3] Testing suggest_robots_for_instruction() returns exactly the real graph's SUITABLE_FOR edges...")
    graph = build_graph_from_registry()
    suggested = suggest_robots_for_instruction("Tighten the M8 bolt", graph=graph)

    expected = {
        e.target_id[len("robot_"):]
        for e in graph.edges
        if e.source_id == "skill_tighten_bolt" and e.relation.value == "SUITABLE_FOR"
    }
    assert set(suggested) == expected
    assert "temi" not in suggested  # no force/torque sensor -- the graph's own real gate
    assert "franka_panda" in suggested
    print(f"  -> {len(suggested)} real graph-suitable robots, exactly matching the graph's own edges [PASSED]")


def test_suggest_robots_for_instruction_builds_its_own_graph_when_none_given():
    print("\n[TEST 4] Testing suggest_robots_for_instruction() builds a real graph when none is passed...")
    suggested = suggest_robots_for_instruction("Pick up the red cube")
    assert len(suggested) > 0
    assert "franka_panda" in suggested
    print(f"  -> {len(suggested)} real robots suggested without a pre-built graph [PASSED]")


if __name__ == "__main__":
    print("=== STARTING GRAPH-DRIVEN COMPILATION VERIFICATION ===")
    test_classify_category_matches_the_real_action_category_map()
    test_classify_category_is_robot_independent()
    test_suggest_robots_for_instruction_matches_the_real_graph_edges()
    test_suggest_robots_for_instruction_builds_its_own_graph_when_none_given()
    print("\n=== ALL GRAPH-DRIVEN COMPILATION TESTS PASSED SUCCESSFULLY ===")
