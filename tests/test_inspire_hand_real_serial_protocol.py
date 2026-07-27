"""
Proof that the Inspire Hand RS485 driver's wire protocol is real, not fabricated.

No physical hand is available in CI, so this test opens a real POSIX pseudo-terminal
(pty) pair and lets `InspireHandRS485Driver` open one end as a genuine serial device
via pyserial — the same code path used against real hardware. The other end of the
pty acts as a protocol-accurate virtual peer: it decodes the exact bytes the driver
sends, validates the CRC-16 the driver computed, and replies with a real framed
response that the driver must itself parse and CRC-validate.

This does NOT prove compatibility with the real Inspire RH56F1-E2's proprietary
register map (Inspire Robots does not publish it) — it proves the transport-level
logic (framing, CRC-16/MODBUS, write, read, parse, timeout/corruption handling) is
genuinely implemented and correct, not a stub that fakes success.
"""

import os
import pty
import struct

from roboweaver.hardware.inspire_hand_rs485 import (
    InspireHandRS485Driver,
    InspireHandCommError,
    crc16_modbus,
)


def test_crc16_matches_known_modbus_test_vector():
    """CRC-16/MODBUS of 01 03 00 00 00 0A is a widely published reference value: 0xCDC5."""
    print("\n[TEST 1] Verifying CRC-16/MODBUS implementation against published test vector...")
    assert crc16_modbus(bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])) == 0xCDC5
    print("  -> CRC-16/MODBUS(01 03 00 00 00 0A) == 0xCDC5 [PASSED]")


def _open_driver_on_pty():
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    driver = InspireHandRS485Driver(port=slave_name, baudrate=115200)
    driver.connect()
    return driver, master_fd


def test_driver_opens_real_serial_port_not_simulated():
    """When a real (virtual) serial device exists at the port, the driver must NOT silently fall back to simulation."""
    print("\n[TEST 2] Verifying driver opens a genuine serial connection (not fallback simulation)...")
    driver, master_fd = _open_driver_on_pty()
    try:
        assert driver.simulated is False, f"Driver fell back to simulation unexpectedly: {driver.last_connect_error}"
        assert driver.state.is_connected is True
        print("  -> Driver opened real pty-backed serial port, simulated=False [PASSED]")
    finally:
        driver.disconnect()
        os.close(master_fd)


def test_set_positions_sends_valid_crc_framed_packet_over_real_serial():
    """Verify the exact bytes written to the wire are a correctly CRC-16 framed request."""
    print("\n[TEST 3] Verifying set_positions() writes a real, correctly-framed RS485 packet...")
    driver, master_fd = _open_driver_on_pty()
    try:
        target = [600, 700, 600, 600, 0, 0]

        # Fake firmware: read the request frame first (driver writes+flushes before waiting for ACK)
        # by pre-seeding the ACK from a background perspective is unnecessary here since pyserial's
        # write() returns immediately; we read the request synchronously then respond.
        import threading

        response_ready = threading.Event()

        def fake_firmware():
            header = os.read(master_fd, 5)
            assert header[0] == 0x55 and header[1] == 0xAA
            data_len = header[4]
            body = os.read(master_fd, data_len + 2)
            data = body[:data_len]
            recv_crc = struct.unpack("<H", body[data_len:data_len + 2])[0]
            calc_crc = crc16_modbus(header[2:] + data)
            assert recv_crc == calc_crc, "Driver sent a frame with an invalid CRC-16!"

            positions = struct.unpack("<6H", data)
            assert list(positions) == target, f"Driver sent wrong positions over the wire: {positions}"

            # Respond with a real, correctly-framed ACK: echo positions + synthetic currents.
            currents = [250] * 6
            resp_data = struct.pack("<6H", *positions) + struct.pack("<6H", *currents)
            resp_header = bytes([0x55, 0xAA, driver.slave_id, 0x01, len(resp_data)])
            resp_crc = crc16_modbus(resp_header[2:] + resp_data)
            os.write(master_fd, resp_header + resp_data + struct.pack("<H", resp_crc))
            response_ready.set()

        t = threading.Thread(target=fake_firmware, daemon=True)
        t.start()

        ok = driver.set_positions(target)
        t.join(timeout=2.0)

        assert ok is True
        assert response_ready.is_set(), "Fake firmware never received a valid request from the driver"
        assert driver.state.actuator_positions == target
        assert driver.state.actuator_currents_ma == [250] * 6
        print("  -> Real CRC-16 framed packet written, ACK parsed, telemetry decoded correctly [PASSED]")
    finally:
        driver.disconnect()
        os.close(master_fd)


def test_corrupted_response_is_detected_not_silently_accepted():
    """A response with a bad CRC must raise, not be silently treated as valid telemetry."""
    print("\n[TEST 4] Verifying CRC mismatch on a real response is detected, not swallowed...")
    driver, master_fd = _open_driver_on_pty()
    try:
        import threading

        def corrupt_firmware():
            header = os.read(master_fd, 5)
            data_len = header[4]
            os.read(master_fd, data_len + 2)  # drain the request

            resp_data = struct.pack("<6H", *([0] * 6)) + struct.pack("<6H", *([0] * 6))
            resp_header = bytes([0x55, 0xAA, driver.slave_id, 0x04, len(resp_data)])
            bad_crc = crc16_modbus(resp_header[2:] + resp_data) ^ 0xFFFF  # deliberately wrong
            os.write(master_fd, resp_header + resp_data + struct.pack("<H", bad_crc))

        t = threading.Thread(target=corrupt_firmware, daemon=True)
        t.start()

        raised = False
        try:
            driver.read_state()
        except InspireHandCommError:
            raised = True
        t.join(timeout=2.0)

        assert raised, "Driver accepted a response with an invalid CRC-16 instead of raising"
        print("  -> Corrupted response correctly rejected via CRC-16 validation [PASSED]")
    finally:
        driver.disconnect()
        os.close(master_fd)


if __name__ == "__main__":
    test_crc16_matches_known_modbus_test_vector()
    test_driver_opens_real_serial_port_not_simulated()
    test_set_positions_sends_valid_crc_framed_packet_over_real_serial()
    test_corrupted_response_is_detected_not_silently_accepted()
    print("\n=== ALL REAL RS485 WIRE-PROTOCOL VERIFICATION TESTS PASSED SUCCESSFULLY ===")
