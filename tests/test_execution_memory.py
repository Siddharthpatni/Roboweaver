"""
Verification suite for episodic execution memory (runtime/memory.py) -- item 6 of
docs/COMPILER_ROADMAP.md's v2 vision.
"""

import tempfile
import threading
from pathlib import Path

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.runtime.engine import SkillRuntime
from roboweaver.runtime.memory import ExecutionMemoryStore


def test_success_rate_is_none_without_history():
    print("\n[TEST 1] Testing success_rate() returns None (not 0.0) on a fresh store...")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        assert store.success_rate("PICK", "franka_panda") is None
    print("  -> None, not a fabricated 0.0, when there's no real history [PASSED]")


def test_skill_runtime_does_not_write_to_disk_by_default():
    print("\n[TEST 2] Testing SkillRuntime.execute() does NOT write to disk by default...")
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        cwd_before = os.getcwd()
        os.chdir(tmpdir)
        try:
            compiler = SkillCompiler(target_robot="franka_panda")
            skill = compiler.compile("Pick up the red cube", verbose=False)
            runtime = SkillRuntime(robot_spec=compiler.robot_spec)  # no memory_store
            runtime.execute(skill, verbose=False)
            assert not (Path(tmpdir) / ".execution_memory").exists()
        finally:
            os.chdir(cwd_before)
    print("  -> no .execution_memory directory created without an explicitly attached store [PASSED]")


def test_skill_runtime_records_a_real_execution_when_store_attached():
    print("\n[TEST 3] Testing SkillRuntime.execute() records a real outcome when a store is attached...")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        compiler = SkillCompiler(target_robot="franka_panda")
        skill = compiler.compile("Pick up the red cube", verbose=False)
        runtime = SkillRuntime(robot_spec=compiler.robot_spec, memory_store=store)
        result = runtime.execute(skill, verbose=False)

        records = store.query(action="PICK", robot_id="franka_panda")
        assert len(records) == 1
        assert records[0]["execution"]["success"] == result.success
        assert records[0]["task"]["object_name"] == "red_cube"

        rate = store.success_rate("PICK", "franka_panda")
        assert rate == (1.0 if result.success else 0.0)
    print(f"  -> real record written and queryable; success_rate={rate} [PASSED]")


def test_success_rate_reflects_multiple_real_runs():
    print("\n[TEST 4] Testing success_rate() reflects several real recorded runs...")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        compiler = SkillCompiler(target_robot="franka_panda")
        skill = compiler.compile("Pick up the red cube", verbose=False)

        for _ in range(3):
            runtime = SkillRuntime(robot_spec=compiler.robot_spec, memory_store=store)
            runtime.execute(skill, verbose=False)

        records = store.query(action="PICK", robot_id="franka_panda")
        assert len(records) == 3
        rate = store.success_rate("PICK", "franka_panda")
        assert rate is not None
        print(f"  -> 3 real runs recorded; success_rate={rate} [PASSED]")


def test_robot_id_cannot_escape_the_store_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        with pytest.raises(ValueError, match="robot_id"):
            store.record({"task": {"robot_id": "../escape", "action": "PICK"}})
        with pytest.raises(ValueError, match="robot_id"):
            store.query(robot_id="../escape")
        assert not (Path(tmpdir).parent / "escape.jsonl").exists()


def test_non_finite_and_oversized_records_are_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        with pytest.raises(ValueError):
            store.record({"task": {"robot_id": "franka_panda"}, "score": float("nan")})
        with pytest.raises(ValueError, match="exceeds"):
            store.record({"task": {"robot_id": "franka_panda"}, "data": "x" * 1_048_576})


def test_corrupt_records_are_skipped_without_losing_valid_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        path = Path(tmpdir) / "franka_panda.jsonl"
        path.write_text(
            '{"task":{"robot_id":"franka_panda","action":"PICK"},"timestamp":1}\n'
            'not-json\n'
            '{"task":{"robot_id":"franka_panda","action":"PICK"},"timestamp":NaN}\n',
            encoding="utf-8",
        )
        records = store.query(robot_id="franka_panda")
        assert len(records) == 1
        assert records[0]["timestamp"] == 1


def test_concurrent_appends_remain_complete_json_lines():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExecutionMemoryStore(store_dir=tmpdir)
        threads = [
            threading.Thread(
                target=store.record,
                args=({"task": {"robot_id": "franka_panda", "action": "PICK"}, "run": index},),
            )
            for index in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert {record["run"] for record in store.query(robot_id="franka_panda", limit=20)} == set(range(20))


@pytest.mark.parametrize("limit", [0, -1, 10_001, True, 1.5])
def test_query_limit_is_bounded(limit):
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="limit"):
            ExecutionMemoryStore(store_dir=tmpdir).query(limit=limit)


if __name__ == "__main__":
    print("=== STARTING EXECUTION MEMORY (ITEM 6) VERIFICATION ===")
    test_success_rate_is_none_without_history()
    test_skill_runtime_does_not_write_to_disk_by_default()
    test_skill_runtime_records_a_real_execution_when_store_attached()
    test_success_rate_reflects_multiple_real_runs()
    print("\n=== ALL EXECUTION MEMORY TESTS PASSED SUCCESSFULLY ===")
