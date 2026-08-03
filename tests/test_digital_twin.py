"""
Verification suite for the DigitalTwin interface (simulation_backends/twin.py) --
item 4 of docs/COMPILER_ROADMAP.md's v2 vision.
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.hardware import get_robot_spec
from roboweaver.simulation_backends import TWIN_REGISTRY, NativeTwin, RemoteTwin


def _real_skill(robot_id: str = "franka_panda"):
    compiler = SkillCompiler(target_robot=robot_id)
    return compiler.compile("Pick up the red cube", verbose=False)


def test_registry_has_both_twins():
    print("\n[TEST 1] Testing both twins are registered as classes (fresh instance per use)...")
    assert set(TWIN_REGISTRY.names()) == {"native", "remote"}
    native = TWIN_REGISTRY.get("native")()
    remote = TWIN_REGISTRY.get("remote")()
    assert isinstance(native, NativeTwin)
    assert isinstance(remote, RemoteTwin)
    print("  -> native/remote registered as classes, instantiate independently [PASSED]")


def test_native_twin_really_executes():
    print("\n[TEST 2] Testing NativeTwin.execute() really runs SkillRuntime (not a stub)...")
    spec = get_robot_spec("franka_panda")
    skill = _real_skill("franka_panda")

    twin = NativeTwin()
    twin.load_robot(spec)
    result = twin.execute(skill)

    assert result.success is True
    assert result.height_gained > 0
    metrics = twin.collect_metrics()
    assert metrics["telemetry_frame_count"] > 0
    print(f"  -> real execution: height_gained={result.height_gained:.3f}m, "
          f"{metrics['telemetry_frame_count']} telemetry frames [PASSED]")


def test_native_twin_requires_load_robot_first():
    print("\n[TEST 3] Testing NativeTwin.execute() before load_robot() raises...")
    twin = NativeTwin()
    try:
        twin.execute(_real_skill())
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    print("  -> RuntimeError raised when load_robot() was never called [PASSED]")


def test_remote_twin_never_fabricates_a_physics_result():
    print("\n[TEST 4] Testing RemoteTwin.execute() honestly reports no real physics ran...")
    spec = get_robot_spec("franka_panda")
    skill = _real_skill("franka_panda")

    twin = RemoteTwin(protocol="sim", uri="sim://127.0.0.1:1")  # nothing listens here
    twin.load_robot(spec)
    result = twin.execute(skill)

    assert result.success is False
    assert "no real physics simulation ran" in result.frames[0]
    print(f"  -> RemoteTwin reports success=False and states plainly: {result.frames[0]} [PASSED]")


if __name__ == "__main__":
    print("=== STARTING DIGITAL TWIN (ITEM 4) VERIFICATION ===")
    test_registry_has_both_twins()
    test_native_twin_really_executes()
    test_native_twin_requires_load_robot_first()
    test_remote_twin_never_fabricates_a_physics_result()
    print("\n=== ALL DIGITAL TWIN TESTS PASSED SUCCESSFULLY ===")
