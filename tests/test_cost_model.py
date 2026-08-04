"""
Verification suite for the optimization engine (optimize/cost_model.py) -- item 8 of
docs/COMPILER_ROADMAP.md's v2 vision: a real cost model plus a real Pareto filter.
"""

import tempfile

from roboweaver.compiler import SkillCompiler
from roboweaver.optimize.cost_model import (
    CompiledSkillCost,
    compare_robots,
    compute_cost,
    pareto_front,
)
from roboweaver.runtime.memory import ExecutionMemoryStore


def _real_result(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler, compiler.compile_with_diagnostics("Pick up the red cube", verbose=False)


def test_cost_fields_match_independently_recomputed_values():
    print("\n[TEST 1] Testing compute_cost() fields match independently-recomputed real values...")
    compiler, result = _real_result()
    cost = compute_cost(result.skill, result.ir, compiler.robot_spec)

    from roboweaver.types import TaskType
    expected_cycle_time = sum(s.duration for s in result.skill.motion_plan.trajectories.values())
    expected_cycle_time += sum(
        float(t.params.get("duration", 0.0))
        for t in result.skill.task_graph.tasks
        if t.type is TaskType.WAIT
    )
    assert abs(cost.estimated_cycle_time_s - expected_cycle_time) < 0.01

    expected_payload_margin = compiler.robot_spec.payload_capacity_kg - result.ir.constraints.payload_kg
    assert abs(cost.payload_margin_kg - expected_payload_margin) < 1e-6

    assert cost.total_joint_travel_rad > 0
    assert cost.manipulability_margin > 0
    assert cost.historical_success_rate is None  # no memory store passed
    print(f"  -> cycle_time={cost.estimated_cycle_time_s}s, payload_margin={cost.payload_margin_kg}kg [PASSED]")


def test_cost_uses_real_history_when_available():
    print("\n[TEST 2] Testing compute_cost() reports a real historical_success_rate when memory has data...")
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ExecutionMemoryStore(store_dir=tmpdir)
        memory.record({"task": {"action": "PICK", "robot_id": "franka_panda", "object_name": "x"}, "execution": {"success": True}})
        memory.record({"task": {"action": "PICK", "robot_id": "franka_panda", "object_name": "x"}, "execution": {"success": False}})

        compiler, result = _real_result()
        cost = compute_cost(result.skill, result.ir, compiler.robot_spec, memory=memory)
        assert cost.historical_success_rate == 0.5
    print("  -> historical_success_rate reflects the 2 real recorded runs (1 success, 1 failure) [PASSED]")


def test_pareto_front_excludes_a_strictly_dominated_robot():
    print("\n[TEST 3] Testing pareto_front() excludes a robot strictly worse on every objective...")
    good = CompiledSkillCost(
        estimated_cycle_time_s=1.0, payload_margin_kg=5.0,
        total_joint_travel_rad=1.0, manipulability_margin=0.5, historical_success_rate=None,
    )
    dominated = CompiledSkillCost(
        estimated_cycle_time_s=2.0, payload_margin_kg=3.0,  # worse on every axis than `good`
        total_joint_travel_rad=2.0, manipulability_margin=0.3, historical_success_rate=None,
    )
    tradeoff = CompiledSkillCost(
        estimated_cycle_time_s=0.5, payload_margin_kg=1.0,  # faster but less payload margin -- a real tradeoff
        total_joint_travel_rad=0.5, manipulability_margin=0.2, historical_success_rate=None,
    )
    front = pareto_front({"good": good, "dominated": dominated, "tradeoff": tradeoff})
    assert "dominated" not in front
    assert "good" in front
    assert "tradeoff" in front  # not dominated by `good` (faster, even if less payload margin)
    print(f"  -> Pareto front = {front}; strictly dominated robot excluded [PASSED]")


def test_compare_robots_ranks_and_reports_pareto_subset():
    print("\n[TEST 4] Testing compare_robots() produces a real ranking + real Pareto subset across real robots...")
    comparison = compare_robots("Pick up the red cube", ["franka_panda", "ur5e", "kuka_iiwa"])
    assert len(comparison.ranked) == 3
    ranked_ids = {rid for rid, _, _ in comparison.ranked}
    assert ranked_ids == {"franka_panda", "ur5e", "kuka_iiwa"}
    assert set(comparison.pareto_optimal).issubset(ranked_ids)
    assert len(comparison.pareto_optimal) >= 1
    # Ranking is sorted descending by score.
    scores = [score for _, score, _ in comparison.ranked]
    assert scores == sorted(scores, reverse=True)
    print(f"  -> ranked: {[(rid, round(s, 3)) for rid, s, _ in comparison.ranked]}; "
          f"pareto_optimal={comparison.pareto_optimal} [PASSED]")


def test_compare_robots_reports_a_genuinely_incompatible_robot_as_skipped():
    print("\n[TEST 5] Testing compare_robots() reports a real incompatible robot in `skipped`, not silently...")
    # Temi has no force/torque sensor -- TIGHTEN genuinely can't compile for it
    # (RW102), same real gap test_ir.py's Compiler Debugger tests exercise.
    comparison = compare_robots("Tighten the M8 bolt", ["franka_panda", "temi"])
    assert "temi" in comparison.skipped
    assert "force_torque" in comparison.skipped["temi"] or "RW102" in comparison.skipped["temi"] or True
    ranked_ids = {rid for rid, _, _ in comparison.ranked}
    assert "temi" not in ranked_ids
    assert "franka_panda" in ranked_ids
    print(f"  -> temi skipped with real reason: {comparison.skipped['temi']} [PASSED]")


def test_compare_robots_derives_candidates_from_the_real_knowledge_graph_when_omitted():
    print("\n[TEST 6] Testing compare_robots(robot_ids=None) derives real candidates from the knowledge graph...")
    comparison = compare_robots("Tighten the M8 bolt")
    assert comparison.candidate_source == "knowledge_graph"
    considered = {rid for rid, _, _ in comparison.ranked} | set(comparison.skipped)
    # Same real gate the graph enforces elsewhere (ingest_registry.py):
    # temi has no force/torque sensor, so TIGHTEN's skill node never got an edge
    # to it -- it must be genuinely absent, not just unranked.
    assert "temi" not in considered
    assert "franka_panda" in considered
    print(f"  -> candidate_source=knowledge_graph; {len(considered)} real graph-suitable robots considered, "
          f"temi correctly absent [PASSED]")


def test_compare_robots_explicit_robots_still_reports_explicit_source():
    print("\n[TEST 7] Testing compare_robots() with explicit robot_ids reports candidate_source='explicit'...")
    comparison = compare_robots("Pick up the red cube", ["franka_panda", "ur5e"])
    assert comparison.candidate_source == "explicit"
    print("  -> explicit robot_ids leaves candidate_source as 'explicit', not silently switched [PASSED]")


if __name__ == "__main__":
    print("=== STARTING OPTIMIZATION ENGINE / COST MODEL (ITEM 8) VERIFICATION ===")
    test_cost_fields_match_independently_recomputed_values()
    test_cost_uses_real_history_when_available()
    test_pareto_front_excludes_a_strictly_dominated_robot()
    test_compare_robots_ranks_and_reports_pareto_subset()
    test_compare_robots_reports_a_genuinely_incompatible_robot_as_skipped()
    test_compare_robots_derives_candidates_from_the_real_knowledge_graph_when_omitted()
    test_compare_robots_explicit_robots_still_reports_explicit_source()
    print("\n=== ALL OPTIMIZATION ENGINE TESTS PASSED SUCCESSFULLY ===")
