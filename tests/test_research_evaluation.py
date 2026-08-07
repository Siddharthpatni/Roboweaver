from roboweaver.research.evaluation import run_research_evaluation


def test_research_evaluation_runs_real_compiler_diagnostics_runtime_and_baseline():
    report = run_research_evaluation().to_dict()

    assert report["benchmark_version"] == "rw-research-v1"
    assert report["passed"] == report["total"] == 6
    metrics = {item["name"]: item for item in report["metrics"]}
    assert metrics["determinism"]["evidence"]["runs"] == 3
    assert len(metrics["target_portability"]["evidence"]["accepted_targets"]) == 3
    assert metrics["diagnostic_precision"]["evidence"]["observed"] == ["RW102"]
    assert metrics["runtime_correctness"]["evidence"]["height_gained_m"] > 0
    assert metrics["planning_performance"]["evidence"]["baseline"] == "RoboWeaver O0"
