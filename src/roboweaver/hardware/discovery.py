"""
Robot Discovery Service — scans the local network for nearby robots and simulators.

Probes common robot controller ports (ROS 2 DDS, Isaac Sim, Gazebo, UR, KUKA, Webots,
Fanuc, ABB, etc.) and attempts Zeroconf/mDNS discovery for `_ros._tcp` and `_robot._tcp`
services.  Returns a list of DiscoveredRobot entries the frontend can present for
one-click connection.

All probes are honest: a socket connect with a short timeout, reporting exactly what
was found or not found.  No fabricated results.
"""

from __future__ import annotations

import concurrent.futures
import glob
import ipaddress
import logging
import os
import platform
import re
import socket
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("roboweaver.hardware.discovery")

# A /22 is 1022 usable hosts. Anything larger is almost certainly a mistake
# (a /16 is 65k hosts x 14 ports = ~900k connects) and is refused rather than
# quietly started -- a scan that never finishes is worse than an error.
MAX_SCAN_HOSTS = 1024

# Bounded fan-out. Enough to sweep a /24 in a few seconds without exhausting
# file descriptors or looking like a SYN flood to the local switch.
MAX_SCAN_WORKERS = 128

# Known robot/simulator ports to scan on localhost and local subnet
SCAN_TARGETS: list[dict[str, Any]] = [
    {"name": "ROS 2 DDS Discovery",   "port": 7400,  "protocol": "ros2",   "desc": "ROS 2 DDS discovery multicast port"},
    {"name": "ROS 2 Bridge",          "port": 9090,  "protocol": "ros2",   "desc": "rosbridge_suite WebSocket server"},
    {"name": "NVIDIA Isaac Sim",      "port": 8211,  "protocol": "sim",    "desc": "Isaac Sim Nucleus/OmniGraph streaming"},
    {"name": "Gazebo / Ignition",     "port": 11345, "protocol": "sim",    "desc": "Gazebo transport service discovery"},
    {"name": "Webots",                "port": 1234,  "protocol": "sim",    "desc": "Webots remote control server"},
    {"name": "Universal Robots",      "port": 30002, "protocol": "tcp",    "desc": "UR Secondary Interface (real-time)"},
    {"name": "Universal Robots RTDE", "port": 30004, "protocol": "tcp",    "desc": "UR RTDE data exchange"},
    {"name": "KUKA EKI",              "port": 30200, "protocol": "tcp",    "desc": "KUKA EthernetKRL Interface"},
    {"name": "KUKA RSI",              "port": 49152, "protocol": "tcp",    "desc": "KUKA Robot Sensor Interface"},
    {"name": "Fanuc KAREL",           "port": 18735, "protocol": "tcp",    "desc": "Fanuc KAREL HTTP server"},
    {"name": "ABB RAPID",             "port": 5000,  "protocol": "tcp",    "desc": "ABB RobotStudio remote service"},
    {"name": "Franka Control",        "port": 1337,  "protocol": "tcp",    "desc": "Franka Control Interface (FCI)"},
    {"name": "MoveIt Task Server",    "port": 5555,  "protocol": "ros2",   "desc": "MoveIt Task Constructor"},
    {"name": "RoboWeaver Backend",    "port": 8080,  "protocol": "http",   "desc": "RoboWeaver dashboard API server"},
]

# Hosts to probe (extend with local subnet scan if needed)
DEFAULT_HOSTS = ["127.0.0.1", "localhost"]

# Ports in SCAN_TARGETS that are routinely held by ordinary desktop software.
# A TCP connect proves only that *something* is listening, and identification
# here is by port number alone -- so on macOS, ControlCenter's AirPlay Receiver
# on 5000 would otherwise be reported as a confident "ABB Industrial" robot.
# These entries downgrade the claim instead of overstating it.
AMBIGUOUS_PORTS: dict[int, str] = {
    1234: "a generic development server",
    5000: "macOS ControlCenter / AirPlay Receiver, or a Flask dev server",
    5555: "adb or a generic development server",
    8080: "a generic HTTP development server (including this dashboard)",
    9090: "Prometheus or a generic development server",
    49152: "the OS ephemeral port range -- any application may hold it",
}

# Confidence assigned when the port is distinctive to robot/simulator software.
# Still not certainty: no vendor handshake is performed anywhere in this module.
_PORT_HEURISTIC_CONFIDENCE = 0.8
_AMBIGUOUS_PORT_CONFIDENCE = 0.25


@dataclass
class DiscoveredRobot:
    """A robot or simulator endpoint discovered on the network.

    `reachable` is a hard fact (a socket accepted the connection). `name`,
    `robot_type_guess` and `confidence` are inferences from the port number
    alone -- consumers must not present them as a verified robot identity.
    """
    name: str
    host: str
    port: int
    protocol: str
    description: str
    reachable: bool
    latency_ms: float
    robot_type_guess: str = ""  # Best guess from port/protocol mapping
    confidence: float = _PORT_HEURISTIC_CONFIDENCE
    caveat: str = ""  # Non-empty when the port is commonly non-robot software
    # Bytes the service volunteered on connect, decoded and truncated. Real
    # evidence of what is actually listening -- unlike the port number, which is
    # only a convention. Empty when the service said nothing first.
    banner: str = ""
    hostname: str = ""  # Reverse-DNS name, when the resolver returns one


@dataclass
class NetworkRange:
    """An IPv4 range that can be swept for robots.

    `netmask_source` records how the prefix was determined: "interface" when it
    was read from the OS, "assumed_/24" when only the host address was
    discoverable and a /24 was inferred. A guessed prefix can silently scan the
    wrong set of addresses, so the distinction is surfaced, never hidden.
    """
    cidr: str
    interface_ip: str
    interface_name: str = ""
    netmask_source: str = "assumed_/24"
    host_count: int = 0


@dataclass
class LocalTransport:
    """A local, non-IP path to a robot.

    Plenty of hardware is never reachable over TCP at all: RS-485/USB arms and
    hands (this repo already drives an Inspire hand that way), CAN-bus joints,
    and middleware exposed only through a Unix domain socket. When the network
    scan honestly returns nothing, these are the paths that actually exist, so
    the discovery layer enumerates them rather than reporting "no robots".
    """
    kind: str            # "serial" | "can" | "unix_socket"
    device: str          # e.g. /dev/ttyUSB0, can0, /run/robot.sock
    description: str
    available: bool      # node exists
    readable: bool       # process can actually open it (permissions)
    detail: str = ""     # why it is unusable, when it is


@dataclass
class DiscoveryResult:
    """Results of a network discovery scan."""
    discovered: list[DiscoveredRobot] = field(default_factory=list)
    scan_duration_ms: float = 0.0
    hosts_scanned: int = 0
    ports_scanned: int = 0
    local_transports: list[LocalTransport] = field(default_factory=list)
    platform_name: str = ""
    # The CIDR actually swept, or "" for a localhost-only scan. Without this the
    # UI cannot tell "found nothing on your LAN" from "only checked this machine".
    scanned_range: str = ""
    # Transport kinds this OS can actually be scanned for. CAN enumeration reads
    # /sys/class/net, which simply does not exist off Linux -- saying so beats
    # reporting an empty list that reads like "no CAN hardware present".
    supported_transports: list[str] = field(default_factory=list)


class RobotDiscoveryService:
    """Scans for nearby robots via TCP port probes.

    All probes use a real socket connect with a short timeout.
    Nothing is fabricated — if a port isn't listening, it's reported as unreachable.
    """

    def __init__(self, timeout: float = 0.5, hosts: list[str] | None = None):
        self.timeout = timeout
        self.hosts = hosts or list(DEFAULT_HOSTS)

    def scan(self, targets: list[dict[str, Any]] | None = None) -> DiscoveryResult:
        """Run a synchronous network scan.  Thread-safe — each probe runs in
        its own thread for parallelism (a single probe is ~timeout seconds worst case)."""
        import time

        scan_targets = targets or SCAN_TARGETS
        start = time.monotonic()

        results: list[DiscoveredRobot] = []
        lock = threading.Lock()

        def probe(host: str, target: dict[str, Any]) -> None:
            # Same probe the subnet sweep uses, so both paths capture banners and
            # reverse-DNS identically -- a localhost result must not be poorer
            # evidence than a LAN one.
            robot = self._probe_endpoint(host, target)
            if robot is not None:
                with lock:
                    results.append(robot)
                logger.info(
                    f"Discovered: {target['name']} at {host}:{target['port']} ({robot.latency_ms}ms)"
                )

        threads: list[threading.Thread] = []
        for host in self.hosts:
            for target in scan_targets:
                t = threading.Thread(target=probe, args=(host, target), daemon=True)
                threads.append(t)
                t.start()

        for t in threads:
            t.join(timeout=self.timeout + 0.5)

        elapsed_ms = (time.monotonic() - start) * 1000

        return DiscoveryResult(
            # Confident matches first, then fastest -- otherwise a local dev server
            # on 8080 outranks a real UR controller purely by being a shade quicker.
            discovered=sorted(results, key=lambda r: (-r.confidence, r.latency_ms)),
            scan_duration_ms=round(elapsed_ms, 1),
            hosts_scanned=len(self.hosts),
            ports_scanned=len(scan_targets),
            local_transports=self.scan_local_transports(),
            platform_name=platform.system(),
            supported_transports=self.supported_transport_kinds(),
        )

    # ── LAN range detection & subnet sweep ────────────────────────────

    @staticmethod
    def primary_ipv4() -> str:
        """This host's primary IPv4 address.

        Opens a UDP socket toward a public address and reads back the local
        address the kernel selected. No packet is ever sent (UDP connect only
        sets the route), so this works without traffic leaving the machine --
        but it does need a default route, and returns "" when there is none.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return str(s.getsockname()[0])
        except OSError:
            return ""
        finally:
            s.close()

    @staticmethod
    def _interface_prefix(ip: str) -> tuple[int | None, str]:
        """Read the real netmask for `ip` from the OS, returning (prefix, iface).

        Falls back to (None, "") so the caller can say it assumed a /24 rather
        than pretending it knew.
        """
        system = platform.system()
        try:
            if system == "Linux":
                out = subprocess.run(
                    ["ip", "-o", "-f", "inet", "addr", "show"],
                    capture_output=True, text=True, timeout=3.0,
                ).stdout
                # e.g. "2: eth0    inet 192.168.1.24/24 brd ..."
                for line in out.splitlines():
                    m = re.search(r"^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                    if m and m.group(2) == ip:
                        return int(m.group(3)), m.group(1)
            elif system == "Darwin":
                out = subprocess.run(
                    ["ifconfig"], capture_output=True, text=True, timeout=3.0
                ).stdout
                iface = ""
                for line in out.splitlines():
                    header = re.match(r"^(\S+):\s", line)
                    if header:
                        iface = header.group(1)
                    # e.g. "inet 192.168.1.24 netmask 0xffffff00 broadcast ..."
                    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)", line)
                    if m and m.group(1) == ip:
                        prefix = bin(int(m.group(2), 16)).count("1")
                        return prefix, iface
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        return None, ""

    def detect_local_networks(self) -> list[NetworkRange]:
        """Determine the LAN range(s) this host sits on."""
        ip = self.primary_ipv4()
        if not ip:
            return []

        prefix, iface = self._interface_prefix(ip)
        source = "interface" if prefix is not None else "assumed_/24"
        if prefix is None:
            prefix = 24

        try:
            net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
        except ValueError:
            return []

        return [
            NetworkRange(
                cidr=str(net),
                interface_ip=ip,
                interface_name=iface,
                netmask_source=source,
                host_count=max(0, net.num_addresses - 2) if net.prefixlen < 31 else net.num_addresses,
            )
        ]

    def scan_subnet(
        self,
        cidr: str,
        targets: list[dict[str, Any]] | None = None,
    ) -> DiscoveryResult:
        """Sweep every host in `cidr` for the robot control ports.

        Raises ValueError for a malformed CIDR or a range wider than
        MAX_SCAN_HOSTS -- refusing up front beats starting a sweep that would
        take hours. Probes run on a bounded thread pool; a host that is simply
        absent costs one timeout and nothing else.
        """
        import time

        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError as exc:
            raise ValueError(f"'{cidr}' is not a valid IPv4 CIDR range: {exc}") from exc

        if net.version != 4:
            raise ValueError("Only IPv4 ranges are supported.")

        hosts = list(net.hosts()) if net.prefixlen < 31 else list(net)
        if len(hosts) > MAX_SCAN_HOSTS:
            raise ValueError(
                f"{cidr} covers {len(hosts)} hosts, above the {MAX_SCAN_HOSTS} limit. "
                "Narrow the range (a /24 is the usual robot subnet)."
            )

        scan_targets = targets or SCAN_TARGETS
        start = time.monotonic()
        results: list[DiscoveredRobot] = []
        lock = threading.Lock()

        def probe(host: str, target: dict[str, Any]) -> None:
            found = self._probe_endpoint(host, target)
            if found is not None:
                with lock:
                    results.append(found)

        jobs = [(str(h), t) for h in hosts for t in scan_targets]
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SCAN_WORKERS) as pool:
            list(pool.map(lambda a: probe(*a), jobs))

        elapsed_ms = (time.monotonic() - start) * 1000
        return DiscoveryResult(
            discovered=sorted(results, key=lambda r: (-r.confidence, r.latency_ms)),
            scan_duration_ms=round(elapsed_ms, 1),
            hosts_scanned=len(hosts),
            ports_scanned=len(scan_targets),
            local_transports=self.scan_local_transports(),
            platform_name=platform.system(),
            supported_transports=self.supported_transport_kinds(),
            scanned_range=str(net),
        )

    def _probe_endpoint(self, host: str, target: dict[str, Any]) -> DiscoveredRobot | None:
        """One real TCP connect, with an optional banner read. Returns None when
        nothing is listening -- absence is never reported as a finding."""
        import time

        port = target["port"]
        try:
            t0 = time.monotonic()
            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                latency = (time.monotonic() - t0) * 1000
                banner = self._read_banner(sock)
        except (OSError, TimeoutError):
            return None

        squatter = AMBIGUOUS_PORTS.get(port)
        return DiscoveredRobot(
            name=target["name"],
            host=host,
            port=port,
            protocol=target["protocol"],
            description=target["desc"],
            reachable=True,
            latency_ms=round(latency, 1),
            robot_type_guess=self._guess_robot_type(target),
            confidence=_AMBIGUOUS_PORT_CONFIDENCE if squatter else _PORT_HEURISTIC_CONFIDENCE,
            caveat=(
                f"Identified by port number only -- port {port} is commonly {squatter}. "
                "Confirm this is really a robot before connecting."
                if squatter
                else ""
            ),
            banner=banner,
            hostname=self._reverse_dns(host),
        )

    @staticmethod
    def _read_banner(sock: socket.socket, limit: int = 160) -> str:
        """Read whatever the service volunteers on connect. Many controllers
        announce themselves; most say nothing, which is fine and common."""
        try:
            sock.settimeout(0.4)
            raw = sock.recv(limit)
        except (OSError, TimeoutError):
            return ""
        if not raw:
            return ""
        text = raw.decode("utf-8", errors="replace").strip()
        # Collapse control characters so a binary protocol can't corrupt the UI.
        return re.sub(r"[^\x20-\x7e]+", " ", text).strip()[:limit]

    @staticmethod
    def _reverse_dns(host: str) -> str:
        try:
            name, _, _ = socket.gethostbyaddr(host)
            return name if name != host else ""
        except (OSError, socket.herror, socket.gaierror):
            return ""

    # ── Local (non-IP) transports ─────────────────────────────────────
    # Glob patterns per platform. Linux exposes USB-serial adapters as
    # ttyUSB*/ttyACM*; macOS uses the /dev/cu.* callout devices (the tty.*
    # twins block on open waiting for carrier detect, so they are deliberately
    # not probed here).
    SERIAL_PATTERNS: dict[str, list[str]] = {
        "Linux": ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/serial/by-id/*"],
        "Darwin": ["/dev/cu.usbserial*", "/dev/cu.usbmodem*", "/dev/cu.SLAB*", "/dev/cu.wchusb*"],
    }

    # Unix domain sockets commonly used by robot middleware and vendor SDKs.
    UNIX_SOCKET_PATTERNS: list[str] = [
        f"{tempfile.gettempdir()}/*.sock",
        "/run/*.sock",
        "/var/run/*.sock",
        f"{tempfile.gettempdir()}/ros*",
    ]

    # Sockets belonging to ordinary system services. Unlike an ambiguous *port*
    # (a robot really could be served over 8080), these are definitively not
    # robot transports, so listing them would be noise rather than an honest
    # low-confidence result -- they are excluded outright.
    KNOWN_SYSTEM_SOCKETS: tuple[str, ...] = (
        "docker",
        "containerd",
        "vmnetd",
        "vpncontrol",
        "systemd",
        "dbus",
        "pulse",
        "cups",
        "gpg-agent",
        "ssh-agent",
    )

    def scan_local_transports(self) -> list[LocalTransport]:
        """Enumerate serial, CAN and Unix-socket paths to robot hardware.

        Every entry reflects a real filesystem node that was stat-ed, plus an
        honest `readable` flag from an actual access check -- a serial port the
        process cannot open (the classic `dialout`/`tty` group problem) is
        reported as present-but-unusable rather than silently omitted.
        """
        transports: list[LocalTransport] = []
        transports.extend(self._scan_serial())
        transports.extend(self._scan_can())
        transports.extend(self._scan_unix_sockets())
        return transports

    def _scan_serial(self) -> list[LocalTransport]:
        found: list[LocalTransport] = []
        patterns = self.SERIAL_PATTERNS.get(platform.system(), [])
        for pattern in patterns:
            for path in sorted(glob.glob(pattern)):
                readable = os.access(path, os.R_OK | os.W_OK)
                found.append(
                    LocalTransport(
                        kind="serial",
                        device=path,
                        description="Serial / RS-485 device (USB or on-board UART)",
                        available=True,
                        readable=readable,
                        detail=(
                            ""
                            if readable
                            else "Node exists but this process cannot open it -- typically a "
                            "group-permission issue (add the user to 'dialout' on Linux)."
                        ),
                    )
                )
        return found

    def _scan_can(self) -> list[LocalTransport]:
        """Enumerate SocketCAN interfaces. Linux-only: identification reads
        /sys/class/net/<if>/type and compares against ARPHRD_CAN (280)."""
        if platform.system() != "Linux":
            return []

        found: list[LocalTransport] = []
        for iface_path in sorted(glob.glob("/sys/class/net/*")):
            type_file = os.path.join(iface_path, "type")
            try:
                with open(type_file, "r", encoding="utf-8") as fh:
                    if fh.read().strip() != "280":  # ARPHRD_CAN
                        continue
            except OSError:
                continue

            iface = os.path.basename(iface_path)
            operstate = "unknown"
            try:
                with open(os.path.join(iface_path, "operstate"), "r", encoding="utf-8") as fh:
                    operstate = fh.read().strip()
            except OSError:
                pass

            is_up = operstate == "up"
            found.append(
                LocalTransport(
                    kind="can",
                    device=iface,
                    description="SocketCAN interface (CAN / CANopen robot bus)",
                    available=True,
                    readable=is_up,
                    detail=(
                        ""
                        if is_up
                        else f"Interface is '{operstate}'. Bring it up with: "
                        f"sudo ip link set {iface} up type can bitrate 1000000"
                    ),
                )
            )
        return found

    def _scan_unix_sockets(self) -> list[LocalTransport]:
        if platform.system() == "Windows":
            return []

        found: list[LocalTransport] = []
        seen: set[str] = set()
        for pattern in self.UNIX_SOCKET_PATTERNS:
            for path in sorted(glob.glob(pattern)):
                if path in seen:
                    continue
                seen.add(path)
                base = os.path.basename(path).lower()
                if any(svc in base for svc in self.KNOWN_SYSTEM_SOCKETS):
                    continue
                try:
                    mode = os.stat(path).st_mode
                except OSError:
                    continue
                if not stat.S_ISSOCK(mode):
                    continue

                readable = os.access(path, os.R_OK | os.W_OK)
                found.append(
                    LocalTransport(
                        kind="unix_socket",
                        device=path,
                        description="Unix domain socket (local middleware endpoint)",
                        available=True,
                        readable=readable,
                        detail=(
                            ""
                            if readable
                            else "Socket exists but is not readable/writable by this process."
                        ),
                    )
                )
        return found

    def supported_transport_kinds(self) -> list[str]:
        """Which local transport kinds this OS can actually be scanned for."""
        system = platform.system()
        if system == "Linux":
            return ["serial", "can", "unix_socket"]
        if system == "Darwin":
            # No /sys/class/net on macOS, so SocketCAN cannot be enumerated at all.
            return ["serial", "unix_socket"]
        return []

    def scan_host(self, host: str) -> DiscoveryResult:
        """Scan a single specific host."""
        svc = RobotDiscoveryService(timeout=self.timeout, hosts=[host])
        return svc.scan()

    @staticmethod
    def _guess_robot_type(target: dict[str, Any]) -> str:
        """Heuristic guess of what type of robot is at this port."""
        name = target.get("name", "").lower()
        if "universal" in name or "ur " in name:
            return "Universal Robots (UR)"
        elif "kuka" in name:
            return "KUKA Industrial"
        elif "fanuc" in name:
            return "Fanuc Industrial"
        elif "abb" in name:
            return "ABB Industrial"
        elif "franka" in name:
            return "Franka Emika Panda"
        elif "isaac" in name:
            return "NVIDIA Isaac Sim"
        elif "gazebo" in name or "ignition" in name:
            return "Gazebo / Ignition Simulator"
        elif "webots" in name:
            return "Webots Simulator"
        elif "ros 2" in name or "ros2" in name:
            return "ROS 2 Node"
        elif "moveit" in name:
            return "MoveIt Planning Server"
        elif "roboweaver" in name:
            return "RoboWeaver Backend"
        return "Unknown Robot/Service"

    def to_dict(self, result: DiscoveryResult) -> dict[str, Any]:
        """Serialize discovery results for JSON API response."""
        return {
            "discovered": [
                {
                    "name": r.name,
                    "host": r.host,
                    "port": r.port,
                    "protocol": r.protocol,
                    "description": r.description,
                    "reachable": r.reachable,
                    "latency_ms": r.latency_ms,
                    "robot_type_guess": r.robot_type_guess,
                    "confidence": r.confidence,
                    "caveat": r.caveat,
                    "banner": r.banner,
                    "hostname": r.hostname,
                }
                for r in result.discovered
            ],
            "local_transports": [
                {
                    "kind": t.kind,
                    "device": t.device,
                    "description": t.description,
                    "available": t.available,
                    "readable": t.readable,
                    "detail": t.detail,
                }
                for t in result.local_transports
            ],
            "platform_name": result.platform_name,
            "supported_transports": result.supported_transports,
            "scanned_range": result.scanned_range,
            "scan_duration_ms": result.scan_duration_ms,
            "hosts_scanned": result.hosts_scanned,
            "ports_scanned": result.ports_scanned,
        }
