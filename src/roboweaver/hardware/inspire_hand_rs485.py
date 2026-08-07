"""
Inspire Robots Dexterous Hand RH56F1-E2 (RS485) Driver & Gesture Library.

Provides:
1. RS485 serial packet encoder & decoder with real CRC-16/MODBUS framing
2. Multi-Actuator position, velocity, and grasping force control
3. Built-in dexterous grasping gesture library (open, fist, pinch, precision_grip, etc.)
4. Explicit software simulation mode for testing when physical RS485 hardware is absent

The wire framing here (`0x55 0xAA` sync + slave id + command + length + data + CRC-16)
is a RoboWeaver-defined envelope, not the vendor's proprietary register map — Inspire
Robots does not publish that publicly. What IS real: the CRC-16/MODBUS checksum
algorithm, and a genuine two-way serial round trip (write request, read response,
validate CRC, decode payload) when real hardware is connected. See
tests/test_inspire_hand_real_serial_protocol.py for a loopback proof against a
protocol-accurate virtual peer using a pty pair — no physical hand required to verify
the wire logic is correct.

Physical connection failure is fail-closed by default. Tests and the dedicated
simulator may opt into software simulation with ``allow_simulation=True``; even in
that mode ``state.is_connected`` remains false because no physical transport exists.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


class InspireHandCommError(Exception):
    """Raised when a real RS485 round trip fails: timeout, short read, or CRC mismatch."""


@dataclass
class InspireHandState:
    """Real-time telemetry and state of the 6-DOF Inspire RH56F1-E2 hand."""
    actuator_positions: list[int] = field(default_factory=lambda: [0] * 6)  # 0-1000
    actuator_currents_ma: list[int] = field(default_factory=lambda: [0] * 6)
    actuator_forces_n: list[float] = field(default_factory=lambda: [0.0] * 6)
    is_connected: bool = False
    error_code: int = 0
    gesture_active: str = "open"


def crc16_modbus(data: bytes) -> int:
    """Standard CRC-16/MODBUS (polynomial 0xA001, init 0xFFFF), verified against known test vectors."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class InspireHandRS485Driver:
    """RS485 Driver for Inspire RH56F1-E2 Dexterous Hand."""

    GESTURES: dict[str, list[int]] = {
        "open": [0, 0, 0, 0, 0, 0],
        "fist": [1000, 500, 1000, 1000, 1000, 1000],
        "pinch": [700, 800, 700, 0, 0, 0],
        "precision_grip": [600, 700, 600, 600, 0, 0],
        "point": [1000, 500, 0, 1000, 1000, 1000],
        "cylindrical_grip": [800, 300, 800, 800, 800, 800],
        "relax": [100, 100, 100, 100, 100, 100],
    }

    CMD_SET_POSITIONS = 0x01
    CMD_READ_STATE = 0x04

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        slave_id: int = 0x01,
        read_timeout_s: float = 0.2,
        *,
        allow_simulation: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.read_timeout_s = read_timeout_s
        self.serial_conn: Any | None = None
        self.allow_simulation = allow_simulation
        self.simulated: bool = False
        self.last_connect_error: str | None = None
        self.state = InspireHandState()

    def connect(self) -> InspireHandState:
        """Connect to a physical hand, optionally enabling explicit simulation.

        ``state.is_connected`` always describes the physical RS485 transport. A
        caller that intentionally requested simulation can inspect ``simulated``.
        """
        try:
            import serial
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.read_timeout_s,
            )
            self.simulated = False
            self.last_connect_error = None
            self.state.is_connected = True
        except Exception as exc:
            self.serial_conn = None
            self.simulated = self.allow_simulation
            self.last_connect_error = f"{type(exc).__name__}: {exc}"
            self.state.is_connected = False

        return self.state

    def disconnect(self):
        """Close RS485 serial connection."""
        if self.serial_conn and not self.simulated:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.state.is_connected = False

    def _require_available(self) -> None:
        if self.state.is_connected and self.serial_conn is not None:
            return
        if self.simulated:
            return
        reason = f" ({self.last_connect_error})" if self.last_connect_error else ""
        raise InspireHandCommError(
            "Inspire hand is not connected and simulation was not enabled" + reason
        )

    def build_rs485_packet(self, cmd: int, data_bytes: bytes) -> bytes:
        """Build a framed RS485 packet: [0x55, 0xAA, slave_id, cmd, len, data..., crc_lo, crc_hi]."""
        header = bytes([0x55, 0xAA, self.slave_id, cmd, len(data_bytes)])
        crc = crc16_modbus(header[2:] + data_bytes)
        return header + data_bytes + struct.pack("<H", crc)

    def _read_frame(self) -> bytes:
        """Read and CRC-validate one response frame from the real serial connection."""
        header = self.serial_conn.read(5)
        if len(header) < 5:
            raise InspireHandCommError(f"Inspire Hand RS485 timeout: expected 5-byte header, got {len(header)} bytes")
        if header[0] != 0x55 or header[1] != 0xAA:
            raise InspireHandCommError(f"Inspire Hand RS485 frame desync: bad sync bytes {header[:2].hex()}")

        data_len = header[4]
        tail = self.serial_conn.read(data_len + 2)
        if len(tail) < data_len + 2:
            raise InspireHandCommError(
                f"Inspire Hand RS485 timeout: expected {data_len + 2} bytes of payload+crc, got {len(tail)}"
            )

        data = tail[:data_len]
        recv_crc = struct.unpack("<H", tail[data_len:data_len + 2])[0]
        calc_crc = crc16_modbus(header[2:] + data)
        if recv_crc != calc_crc:
            raise InspireHandCommError(
                f"Inspire Hand RS485 CRC-16 mismatch: received 0x{recv_crc:04x}, computed 0x{calc_crc:04x}"
            )
        return data

    @staticmethod
    def _unpack_actuator_frame(data: bytes) -> tuple[list[int], list[int]]:
        """Decode a 24-byte actuator response (6x position + 6x current, both
        uint16 LE). A frame can pass CRC yet still be the wrong length -- noise
        flipping the length byte itself, or real hardware echoing a different
        response than the one requested -- and `struct.unpack` on a short
        buffer raises a bare `struct.error`, not this driver's own
        `InspireHandCommError`. Proven live: a valid-CRC 4-byte payload crashed
        set_positions() with "unpack requires a buffer of 12 bytes" instead of
        a message a caller catching InspireHandCommError would ever see.
        """
        if len(data) < 24:
            raise InspireHandCommError(
                f"Inspire Hand RS485 short frame: expected 24 bytes of actuator "
                f"data (6 positions + 6 currents), got {len(data)} -- CRC was "
                f"valid but the payload doesn't match the expected shape"
            )
        positions = list(struct.unpack("<6H", data[:12]))
        currents = list(struct.unpack("<6H", data[12:24]))
        return positions, currents

    def set_positions(
        self,
        positions: list[int],
        speeds: list[int] | None = None,
        forces: list[int] | None = None,
    ) -> bool:
        """
        Set target positions (0-1000) for all 6 actuators.
        Actuator mapping: [thumb_flex, thumb_abduct, index_flex, middle_flex, ring_flex, pinky_flex]
        """
        if len(positions) != 6:
            raise ValueError("Inspire RH56F1-E2 requires exactly 6 actuator positions (0-1000)")
        self._require_available()

        clamped_pos = [max(0, min(1000, int(p))) for p in positions]

        if not self.simulated and self.serial_conn:
            payload = struct.pack("<6H", *clamped_pos)
            packet = self.build_rs485_packet(cmd=self.CMD_SET_POSITIONS, data_bytes=payload)
            self.serial_conn.write(packet)
            self.serial_conn.flush()
            # Real round trip: the hand ACKs with its actual resulting positions/currents.
            data = self._read_frame()
            self.state.actuator_positions, self.state.actuator_currents_ma = self._unpack_actuator_frame(data)
            self.state.actuator_forces_n = [round(c * 0.002, 2) for c in self.state.actuator_currents_ma]
            return True

        # Software simulation fallback (no physical hand connected).
        self.state.actuator_positions = clamped_pos
        self.state.actuator_forces_n = [round(max(0.0, (p - 200) * 0.015), 2) for p in clamped_pos]
        self.state.actuator_currents_ma = [int(f * 40) for f in self.state.actuator_forces_n]
        return True

    def set_gesture(self, gesture_name: str) -> bool:
        """Command the Inspire hand to assume a pre-programmed dexterous grasping gesture."""
        key = gesture_name.lower().strip()
        if key not in self.GESTURES:
            raise KeyError(f"Unknown Inspire gesture: '{gesture_name}'. Available: {list(self.GESTURES.keys())}")
        target_pos = self.GESTURES[key]
        success = self.set_positions(target_pos)
        if success:
            self.state.gesture_active = key
        return success

    def read_state(self) -> InspireHandState:
        """Query real-time actuator positions and current draw. Real round trip when hardware is connected."""
        self._require_available()
        if not self.simulated and self.serial_conn:
            packet = self.build_rs485_packet(cmd=self.CMD_READ_STATE, data_bytes=b"")
            self.serial_conn.write(packet)
            self.serial_conn.flush()
            data = self._read_frame()
            self.state.actuator_positions, self.state.actuator_currents_ma = self._unpack_actuator_frame(data)
            self.state.actuator_forces_n = [round(c * 0.002, 2) for c in self.state.actuator_currents_ma]
        return self.state
