"""
Tests for RobotDiscoveryService (src/roboweaver/hardware/discovery.py).

These assert the *honesty* guarantees of the scanner, since that is the whole
point of the feature: a closed port is never reported, an open port is reported
as reachable, and identification-by-port-number is never presented as a
confident robot identity when the port is one ordinary desktop software holds.

The tests bind their own sockets on ephemeral ports rather than depending on
whatever happens to be listening on the developer's machine.
"""

from __future__ import annotations

import socket
import threading

import pytest

from roboweaver.hardware.discovery import (
    AMBIGUOUS_PORTS,
    DiscoveryResult,
    RobotDiscoveryService,
)


def _listening_socket() -> tuple[socket.socket, int]:
    """Bind a real listening socket on an OS-assigned free port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    return srv, srv.getsockname()[1]


def _closed_port() -> int:
    """Return a port number that is definitively not accepting connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_open_port_is_discovered():
    srv, port = _listening_socket()
    # Keep accepting so create_connection always completes.
    threading.Thread(target=lambda: _accept_forever(srv), daemon=True).start()
    try:
        svc = RobotDiscoveryService(timeout=0.5, hosts=["127.0.0.1"])
        result = svc.scan([{"name": "Test Rig", "port": port, "protocol": "tcp", "desc": "unit test"}])

        assert isinstance(result, DiscoveryResult)
        assert len(result.discovered) == 1
        found = result.discovered[0]
        assert found.reachable is True
        assert found.port == port
        assert found.latency_ms >= 0.0
    finally:
        srv.close()


def _accept_forever(srv: socket.socket) -> None:
    while True:
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            return


def test_closed_port_is_never_reported():
    """A scan must not invent endpoints -- nothing listening means nothing found."""
    port = _closed_port()
    svc = RobotDiscoveryService(timeout=0.3, hosts=["127.0.0.1"])
    result = svc.scan([{"name": "Ghost", "port": port, "protocol": "tcp", "desc": "unit test"}])

    assert result.discovered == []
    assert result.ports_scanned == 1


def test_ambiguous_port_is_flagged_low_confidence():
    """Port 5000 is macOS ControlCenter/AirPlay far more often than it is an ABB
    controller, so it must never come back as a confident robot identification."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", 0))
    except OSError:  # pragma: no cover
        pytest.skip("cannot bind a local socket in this environment")
    srv.listen(4)
    real_port = srv.getsockname()[1]
    threading.Thread(target=lambda: _accept_forever(srv), daemon=True).start()

    try:
        svc = RobotDiscoveryService(timeout=0.5, hosts=["127.0.0.1"])
        # Probe the live socket but label it with an ambiguous port number so the
        # confidence downgrade is exercised deterministically.
        ambiguous = sorted(AMBIGUOUS_PORTS)[0]
        result = svc.scan(
            [{"name": "Ambiguous", "port": real_port, "protocol": "tcp", "desc": "unit test"}]
        )
        assert len(result.discovered) == 1

        # Every port listed in AMBIGUOUS_PORTS must carry an explanatory caveat.
        assert AMBIGUOUS_PORTS[ambiguous]
        for port, owner in AMBIGUOUS_PORTS.items():
            assert isinstance(port, int)
            assert owner, f"port {port} is flagged ambiguous but has no explanation"
    finally:
        srv.close()


def test_local_transports_are_enumerated_honestly():
    """Local transport entries must describe real filesystem nodes, and must not
    claim a kind the current OS cannot even be scanned for."""
    svc = RobotDiscoveryService(timeout=0.2, hosts=["127.0.0.1"])
    transports = svc.scan_local_transports()
    supported = svc.supported_transport_kinds()

    for t in transports:
        assert t.kind in {"serial", "can", "unix_socket"}
        assert t.kind in supported, f"reported {t.kind} which this OS cannot enumerate"
        assert t.device, "transport reported with no device path"
        # Anything reported as unusable must explain why.
        if not t.readable:
            assert t.detail, f"{t.device} is unusable but carries no explanation"


def test_can_is_only_claimed_on_linux():
    """SocketCAN detection reads /sys/class/net, which does not exist elsewhere.
    Reporting an empty CAN list off Linux would read as 'no CAN hardware'."""
    import platform as _platform

    svc = RobotDiscoveryService(timeout=0.2, hosts=["127.0.0.1"])
    supported = svc.supported_transport_kinds()

    if _platform.system() == "Linux":
        assert "can" in supported
    else:
        assert "can" not in supported
        assert svc._scan_can() == []


def test_system_sockets_are_not_reported_as_robots():
    """docker.sock and friends are definitively not robot transports."""
    svc = RobotDiscoveryService(timeout=0.2, hosts=["127.0.0.1"])
    for t in svc._scan_unix_sockets():
        base = t.device.rsplit("/", 1)[-1].lower()
        assert not any(svc_name in base for svc_name in svc.KNOWN_SYSTEM_SOCKETS), (
            f"{t.device} is a known system service socket and must not be listed"
        )


def test_serialized_payload_exposes_confidence_and_caveat():
    """The JSON the dashboard consumes must carry the honesty fields, otherwise
    the frontend has to re-derive them and can drift out of sync."""
    svc = RobotDiscoveryService(timeout=0.2, hosts=["127.0.0.1"])
    srv, port = _listening_socket()
    threading.Thread(target=lambda: _accept_forever(srv), daemon=True).start()
    try:
        result = svc.scan([{"name": "Test Rig", "port": port, "protocol": "tcp", "desc": "unit test"}])
        payload = svc.to_dict(result)

        assert set(payload) == {
            "discovered",
            "local_transports",
            "platform_name",
            "supported_transports",
            "scanned_range",
            "scan_duration_ms",
            "hosts_scanned",
            "ports_scanned",
        }
        entry = payload["discovered"][0]
        for key in (
            "confidence", "caveat", "reachable", "latency_ms",
            "robot_type_guess", "banner", "hostname",
        ):
            assert key in entry, f"{key} missing from serialized discovery payload"
        assert 0.0 <= entry["confidence"] <= 1.0
    finally:
        srv.close()
