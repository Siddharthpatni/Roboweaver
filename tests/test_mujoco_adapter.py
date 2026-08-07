import pytest

from roboweaver.research.experiments import (
    ExperimentSpec,
    JointSpec,
    LinkSpec,
    TrainingSpec,
    _climbing_monkey_spec,
    _generic_spec,
)
from roboweaver.research.mujoco_adapter import build_mjcf, run_physics_rollout

mujoco = pytest.importorskip("mujoco")


def test_build_mjcf_is_loadable_for_branched_and_chain_specs():
    for spec in (_climbing_monkey_spec("climb"), _generic_spec("do a task")):
        model = mujoco.MjModel.from_xml_string(build_mjcf(spec))
        assert model.nbody == len(spec.links) + 1  # +1 for MuJoCo's implicit world body
        assert model.nu == sum(1 for joint in spec.joints if joint.joint_type != "fixed")


def test_climbing_monkey_rollout_executes_real_physics():
    spec = _climbing_monkey_spec("climb a tree")
    result = run_physics_rollout(spec, max_steps=300, seed=1)

    assert result.status == "executed"
    assert result.numerically_stable is True
    assert result.steps_executed == 300
    assert result.mujoco_version is not None
    assert result.model_bodies == len(spec.links) + 1
    assert result.actuated_joints == len(spec.joints)
    # Gravity must have actually moved the free-floating root body.
    assert result.root_height_end_m < result.root_height_start_m


def test_rollout_is_deterministic_for_a_fixed_seed():
    spec = _generic_spec("repeat this exactly")
    first = run_physics_rollout(spec, max_steps=150, seed=7).to_dict()
    second = run_physics_rollout(spec, max_steps=150, seed=7).to_dict()
    del first["wall_time_s"], second["wall_time_s"]  # wall-clock timing is not deterministic

    assert first == second


def test_rollout_handles_single_link_and_all_fixed_morphologies():
    solo = ExperimentSpec(
        "solo", "test", "single_body",
        (LinkSpec("base", "sphere", (0.2, 0.2, 0.2), 1.0),), (), ("imu",),
        TrainingSpec("PPO", ("s",), ("r",), ("t",), 10),
    )
    assert run_physics_rollout(solo, max_steps=20).status == "executed"

    rigid = ExperimentSpec(
        "rigid", "test", "rigid",
        (LinkSpec("base", "box", (0.3, 0.3, 0.1), 2.0), LinkSpec("tip", "box", (0.1, 0.1, 0.1), 0.2)),
        (JointSpec("j", "base", "tip", "fixed", (0, 0, 1), 0, 0, 1, 1),),
        ("imu",), TrainingSpec("PPO", ("s",), ("r",), ("t",), 10),
    )
    rigid_result = run_physics_rollout(rigid, max_steps=20)
    assert rigid_result.status == "executed"
    assert rigid_result.actuated_joints == 0


def test_rollout_rejects_out_of_bounds_step_counts():
    spec = _generic_spec("bounds check")
    with pytest.raises(ValueError, match="max_steps"):
        run_physics_rollout(spec, max_steps=0)
    with pytest.raises(ValueError, match="max_steps"):
        run_physics_rollout(spec, max_steps=20_001)


def test_rollout_reports_unavailable_without_mujoco(monkeypatch):
    import roboweaver.research.mujoco_adapter as adapter

    monkeypatch.setattr(adapter, "MUJOCO_AVAILABLE", False)
    result = adapter.run_physics_rollout(_generic_spec("no mujoco here"))

    assert result.status == "unavailable_mujoco_not_installed"
    assert result.mujoco_version is None
    assert result.steps_executed == 0
