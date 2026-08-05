"""
Verification suite for GET /api/diff -- the real cross-robot RoboIR diff endpoint
backing the Compiler Studio frontend's diff view. Mirrors
cli/main.py::cmd_diff()'s --robot2 path exactly (ir/diff.py::diff_ir()). Spins up
a real ReusableHTTPServer on an ephemeral port and drives it with real HTTP
requests -- nothing here mocks the handler.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from roboweaver.dashboard.server import ReusableHTTPServer, DashboardHTTPRequestHandler
from roboweaver.ir.diff import diff_ir
from roboweaver.compiler import SkillCompiler


@pytest.fixture
def live_server():
    httpd = ReusableHTTPServer(("127.0.0.1", 0), DashboardHTTPRequestHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_diff_reports_real_field_changes_between_two_real_robots(live_server):
    print("\n[TEST 1] Testing /api/diff reports real field_changes between two real robots' RoboIR...")
    status, body = _get(
        f"{live_server}/api/diff?instruction=Pick+up+the+red+cube&robot=franka_panda&robot2=ur5e"
    )
    assert status == 200
    assert body["from_robot"] == "franka_panda"
    assert body["to_robot"] == "ur5e"
    assert "execution.dof" in body["field_changes"]
    dof_before, dof_after = body["field_changes"]["execution.dof"]
    assert dof_before == 7  # franka_panda is 7-DOF
    assert dof_after == 6  # ur5e is 6-DOF
    print(f"  -> real execution.dof change: {dof_before} -> {dof_after} [PASSED]")


def test_diff_response_matches_independently_computed_diff_ir(live_server):
    print("\n[TEST 2] Testing /api/diff's response matches a real, independently-computed diff_ir()...")
    instruction = "Pick up the red cube"
    status, body = _get(f"{live_server}/api/diff?instruction={instruction.replace(' ', '+')}&robot=franka_panda&robot2=kuka_iiwa")
    assert status == 200

    r1 = SkillCompiler(target_robot="franka_panda").compile_with_diagnostics(instruction, verbose=False)
    r2 = SkillCompiler(target_robot="kuka_iiwa").compile_with_diagnostics(instruction, verbose=False)
    expected = diff_ir(r1.ir, r2.ir)

    assert set(body["field_changes"].keys()) == set(expected.field_changes.keys())
    for k, (old, new) in expected.field_changes.items():
        assert body["field_changes"][k] == [old, new]
    print("  -> real /api/diff response exactly matches a fresh, independent diff_ir() call [PASSED]")


def test_diff_requires_robot2(live_server):
    print("\n[TEST 3] Testing /api/diff rejects a request missing robot2...")
    status, body = _get(f"{live_server}/api/diff?instruction=Pick+up+the+red+cube&robot=franka_panda")
    assert status == 400
    assert "robot2" in body["error"]
    print("  -> real 400 when robot2 is omitted, no compile attempted [PASSED]")


def test_diff_reports_a_real_compilation_failure_for_an_incompatible_robot(live_server):
    print("\n[TEST 4] Testing /api/diff reports a real compilation failure, not a fabricated diff...")
    # Temi has no force/torque sensor -- TIGHTEN genuinely can't compile for it (RW102).
    status, body = _get(
        f"{live_server}/api/diff?instruction=Tighten+the+M8+bolt&robot=franka_panda&robot2=temi"
    )
    assert status == 400
    assert body["error"] == "compilation_failed"
    assert body["robot"] == "temi"
    assert any(d["code"] == "RW102" for d in body["diagnostics"])
    print(f"  -> real RW102 compilation failure surfaced, not a silently empty/fake diff [PASSED]")


if __name__ == "__main__":
    print("=== STARTING /api/diff ROUTE VERIFICATION ===")
    pytest.main([__file__, "-v"])
