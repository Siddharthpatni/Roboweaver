"""Reproducibility contracts for compiler motion lowering."""

from roboweaver.hardware import get_robot_spec
from roboweaver.hardware.kinematics_ndof import NDOFIKSolver


def test_multiseed_ik_is_reproducible_without_global_random_state():
    solver = NDOFIKSolver(get_robot_spec("franka_panda"))
    first = solver.solve([0.32, 0.04, 0.18])
    second = solver.solve([0.32, 0.04, 0.18])

    assert first == second


def test_deterministic_seeds_are_stable_and_distinct():
    solver = NDOFIKSolver(get_robot_spec("ur5e"))
    seeds = [solver._deterministic_seed(index) for index in range(4)]

    assert seeds == [solver._deterministic_seed(index) for index in range(4)]
    assert len({tuple(seed) for seed in seeds}) == len(seeds)
