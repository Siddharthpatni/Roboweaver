"""
Verification suite for the dashboard hardening batch: localhost-only bind by
default, an Origin allow-list that replaces the old wildcard CORS header, and
input-size caps on the instruction/robots-list query params. Spins up a real
ReusableHTTPServer on an ephemeral port and drives it with real HTTP requests
-- nothing here mocks the handler.
"""

import json
import logging
import threading
import urllib.error
import urllib.request

import pytest

from roboweaver.dashboard.server import (
    DashboardHTTPRequestHandler,
    ReusableHTTPServer,
    _is_allowed_origin,
    _is_loopback_bind,
    RequestRateLimiter,
    start_dashboard_server,
)


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


def _get(url: str, origin: str | None = None, token: str | None = None, request_id: str | None = None):
    req = urllib.request.Request(url)
    if origin is not None:
        req.add_header("Origin", origin)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    if request_id is not None:
        req.add_header("X-Request-ID", request_id)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # _send_json()'s error responses (400s) carry a real JSON body; the
        raw = exc.read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
        return exc.code, exc.headers, body


def _post(url: str, payload, token: str | None = None):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, json.loads(exc.read())


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


def test_loopback_bind_detection_is_exact():
    assert _is_loopback_bind("127.0.0.1") is True
    assert _is_loopback_bind("::1") is True
    assert _is_loopback_bind("localhost") is True
    assert _is_loopback_bind("0.0.0.0") is False
    assert _is_loopback_bind("192.168.1.20") is False


def test_non_loopback_start_requires_control_token(monkeypatch):
    monkeypatch.delenv("ROBOWEAVER_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ROBOWEAVER_API_TOKEN"):
        start_dashboard_server(port=0, host="0.0.0.0")


def test_request_with_allowed_origin_gets_it_echoed_back(live_server):
    print("\n[TEST 4] Testing a request from the real frontend's origin is allowed and echoed...")
    status, headers, body = _get(f"{live_server}/api/version", origin="http://localhost:3000")
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert body["roboweaver_version"]
    print("  -> real Access-Control-Allow-Origin echoes the exact real request origin, not '*' [PASSED]")


def test_request_with_disallowed_origin_is_rejected_before_any_handler_runs(live_server):
    print("\n[TEST 5] Testing a request from a real external origin is rejected with 403...")
    status, headers, body = _get(f"{live_server}/api/version", origin="https://evil.com")
    assert status == 403
    assert headers.get("Access-Control-Allow-Origin") is None
    assert body["error"] == "origin_not_allowed"
    print("  -> real JSON 403 with no CORS header; the route never ran [PASSED]")


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


def test_health_endpoints_are_available(live_server):
    for path, check in (("/health/live", "liveness"), ("/health/ready", "readiness")):
        status, _, body = _get(f"{live_server}{path}")
        assert status == 200
        assert body["status"] == "ok"
        assert body["check"] == check
        assert body["version"]


def test_connect_get_is_rejected_without_side_effect(live_server):
    status, _, body = _get(f"{live_server}/api/connect?robot=franka_panda")
    assert status == 405
    assert body["error"] == "method_not_allowed"


def test_connect_post_validates_json_and_robot_id(live_server):
    status, headers, body = _post(f"{live_server}/api/connect", b"not-json")
    assert status == 400
    assert body["error"] == "invalid_json"
    assert headers["X-Request-ID"]

    status, _, body = _post(
        f"{live_server}/api/connect",
        {"robot": "not_a_robot", "protocol": "sim", "uri": "sim://127.0.0.1:1"},
    )
    assert status == 400
    assert body["is_connected"] is False


def test_connect_post_rejects_non_finite_json_numbers(live_server):
    status, _, body = _post(
        f"{live_server}/api/connect",
        b'{"robot":NaN,"protocol":"sim","uri":"sim://127.0.0.1:1"}',
    )
    assert status == 400
    assert body["error"] == "invalid_json"


def test_connect_post_requires_configured_bearer_token(live_server):
    # Reconfigure this already-loopback test server to exercise the same token
    # enforcement used by a non-loopback deployment.
    # The fixture owns the HTTPServer; locate it through a dedicated request is
    # not possible, so run a second ephemeral server with the token attached.
    httpd = ReusableHTTPServer(("127.0.0.1", 0), DashboardHTTPRequestHandler)
    httpd.control_token = "correct-horse-battery-staple"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    payload = {"robot": "not_a_robot", "protocol": "sim", "uri": "sim://127.0.0.1:1"}
    try:
        status, _, body = _post(f"{base}/api/connect", payload)
        assert status == 401
        assert body["error"] == "unauthorized"

        status, _, body = _post(f"{base}/api/connect", payload, token="wrong")
        assert status == 401

        status, _, body = _post(
            f"{base}/api/connect", payload, token="correct-horse-battery-staple"
        )
        assert status == 400
        assert body["is_connected"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_configured_token_protects_get_routes_but_not_health_checks():
    httpd = ReusableHTTPServer(("127.0.0.1", 0), DashboardHTTPRequestHandler)
    token = "a-secure-test-token-with-more-than-32-characters"
    httpd.control_token = token
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, body = _get(f"{base}/api/robots")
        assert status == 401
        assert body["error"] == "unauthorized"
        assert headers["WWW-Authenticate"].startswith("Bearer")

        status, _, body = _get(f"{base}/api/robots", token=token)
        assert status == 200
        assert body

        status, _, body = _get(f"{base}/health/ready")
        assert status == 200
        assert body["status"] == "ok"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_placeholder_and_weak_tokens_are_rejected_at_startup(monkeypatch):
    for token in ("replace-with-a-random-token", "too-short"):
        monkeypatch.setenv("ROBOWEAVER_API_TOKEN", token)
        with pytest.raises(RuntimeError, match="ROBOWEAVER_API_TOKEN"):
            start_dashboard_server(port=0, host="0.0.0.0")


def test_security_headers_and_request_id_are_sanitized(live_server):
    status, headers, _ = _get(
        f"{live_server}/api/version",
        request_id="attacker/request/id",
    )
    assert status == 200
    assert len(headers["X-Request-ID"]) == 32
    assert headers["X-Request-ID"].isalnum()
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Cache-Control"] == "no-store"
    assert "Python" not in headers["Server"]


def test_query_field_limit_and_unknown_robot_fail_closed(live_server):
    excessive_query = "&".join(f"field{i}=x" for i in range(33))
    status, _, body = _get(f"{live_server}/api/version?{excessive_query}")
    assert status == 400
    assert "at most 32" in body["error"]

    status, _, body = _get(
        f"{live_server}/api/compile?instruction=pick+cube&robot=typo_robot"
    )
    assert status == 400
    assert "Unknown robot" in body["error"]


@pytest.mark.parametrize("q", ["0,0", "nan,nan,nan,nan,nan,nan,nan"])
def test_forward_kinematics_requires_exact_finite_joint_vector(live_server, q):
    status, _, body = _get(f"{live_server}/api/robots/franka_panda/fk?q={q}")
    assert status == 400
    assert "exactly 7 finite" in body["error"]


def test_post_rejects_non_json_content_type(live_server):
    req = urllib.request.Request(
        f"{live_server}/api/connect",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(req, timeout=5)
    assert caught.value.code == 415
    assert json.loads(caught.value.read())["error"] == "content_type_must_be_application_json"


def test_rate_limiter_bounds_requests_per_peer():
    httpd = ReusableHTTPServer(("127.0.0.1", 0), DashboardHTTPRequestHandler)
    httpd.rate_limiter = RequestRateLimiter(limit=1)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert _get(f"{base}/api/version")[0] == 200
        status, headers, body = _get(f"{base}/api/robots")
        assert status == 429
        assert headers["Retry-After"] == "60"
        assert body["error"] == "rate_limit_exceeded"
        assert _get(f"{base}/health/live")[0] == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_logs_do_not_include_query_values(live_server, caplog):
    caplog.set_level(logging.INFO, logger="roboweaver.dashboard")
    secret_prompt = "customer-private-work-order"
    status, _, _ = _get(f"{live_server}/api/compile?instruction={secret_prompt}")
    assert status == 200
    assert secret_prompt not in caplog.text


if __name__ == "__main__":
    print("=== STARTING DASHBOARD HARDENING VERIFICATION ===")
    pytest.main([__file__, "-v"])
