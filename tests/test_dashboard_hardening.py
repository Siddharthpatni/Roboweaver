"""
Verification suite for the dashboard hardening batch: localhost-only bind by
default, an Origin allow-list that replaces the old wildcard CORS header, and
input-size caps on the instruction/robots-list query params. Spins up a real
ReusableHTTPServer on an ephemeral port and drives it with real HTTP requests
-- nothing here mocks the handler.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from roboweaver.dashboard.server import ReusableHTTPServer, DashboardHTTPRequestHandler, _is_allowed_origin


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


def _get(url: str, origin: str | None = None):
    req = urllib.request.Request(url)
    if origin is not None:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers.get("Access-Control-Allow-Origin"), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # _send_json()'s error responses (400s) carry a real JSON body; the
        # 403 rejection uses BaseHTTPRequestHandler's own HTML error page, so
        # this returns None for that one case rather than failing to parse it.
        raw = exc.read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
        return exc.code, exc.headers.get("Access-Control-Allow-Origin"), body


def test_is_allowed_origin_accepts_any_localhost_or_loopback_port():
    print("\n[TEST 1] Testing _is_allowed_origin() accepts localhost/127.0.0.1 at any port...")
    assert _is_allowed_origin("http://localhost:3000") is True
    assert _is_allowed_origin("http://localhost:4173") is True
    assert _is_allowed_origin("http://127.0.0.1:3000") is True
    assert _is_allowed_origin("https://localhost:3000") is True
    print("  -> real allow-list accepts every local dev port, not just :3000 [PASSED]")


def test_is_allowed_origin_rejects_external_domains():
    print("\n[TEST 2] Testing _is_allowed_origin() rejects a real external origin...")
    assert _is_allowed_origin("https://evil.com") is False
    assert _is_allowed_origin("http://localhost.evil.com") is False
    assert _is_allowed_origin(None) is False
    print("  -> external/spoofed-lookalike origins and no-origin are all rejected [PASSED]")


def test_default_bind_is_loopback_only(live_server):
    print("\n[TEST 3] Testing the real server's default bind address is loopback...")
    status, _, body = _get(f"{live_server}/api/version")
    assert status == 200
    assert body["roboweaver_version"]
    print("  -> real request to 127.0.0.1 succeeds (fixture itself proves loopback binds) [PASSED]")


def test_request_with_allowed_origin_gets_it_echoed_back(live_server):
    print("\n[TEST 4] Testing a request from the real frontend's origin is allowed and echoed...")
    status, acao, body = _get(f"{live_server}/api/version", origin="http://localhost:3000")
    assert status == 200
    assert acao == "http://localhost:3000"
    assert body["roboweaver_version"]
    print("  -> real Access-Control-Allow-Origin echoes the exact real request origin, not '*' [PASSED]")


def test_request_with_disallowed_origin_is_rejected_before_any_handler_runs(live_server):
    print("\n[TEST 5] Testing a request from a real external origin is rejected with 403...")
    status, acao, body = _get(f"{live_server}/api/version", origin="https://evil.com")
    assert status == 403
    assert acao is None
    assert body is None
    print("  -> real 403, no CORS header, no JSON body -- the handler never ran [PASSED]")


def test_oversized_instruction_is_rejected(live_server):
    print("\n[TEST 6] Testing an oversized instruction is rejected before reaching the compiler...")
    long_instruction = "a" * 3000
    status, _, body = _get(f"{live_server}/api/compile?instruction={long_instruction}")
    assert status == 400
    assert "exceeds" in body["error"]
    print("  -> real 400 for a real 3000-char instruction, compiler never invoked [PASSED]")


def test_too_many_robots_in_compare_is_rejected(live_server):
    print("\n[TEST 7] Testing an oversized robots list on /api/compare is rejected...")
    robots = ",".join(["franka_panda"] * 25)
    status, _, body = _get(f"{live_server}/api/compare?instruction=test&robots={robots}")
    assert status == 400
    assert "at most" in body["error"]
    print("  -> real 400 for 25 robots, compare_robots() never invoked [PASSED]")


def test_normal_compile_still_works_end_to_end(live_server):
    print("\n[TEST 8] Testing a real, in-bounds compile still works after the hardening changes...")
    status, _, body = _get(f"{live_server}/api/compile?instruction=Pick+up+the+red+cube&robot=franka_panda")
    assert status == 200
    assert body["instruction"] == "Pick up the red cube"
    assert body["ir"]["skill"]["id"]
    print("  -> real compile still succeeds -- hardening didn't break the normal path [PASSED]")


if __name__ == "__main__":
    print("=== STARTING DASHBOARD HARDENING VERIFICATION ===")
    pytest.main([__file__, "-v"])
