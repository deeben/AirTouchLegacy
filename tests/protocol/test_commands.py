"""Command frames, checked byte for byte against the reference projects."""

from protocol import commands
import pytest


def test_request_status_matches_homebridge_init() -> None:
    # Homebridge getInitMsg(): [85, 1, 12, 0 x 9, checksum]
    assert commands.request_status() == bytes([85, 1, 12] + [0] * 9 + [98])


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        # toggleAcOnOff(0): buffer[1] = -122 (0x86), buffer[4] = -128 (0x80)
        (commands.toggle_ac(0), "55 86 0c 00 80 00 00 00 00 00 00 00 67"),
        # vzduch SetNewTemperature: up = -93 (0xa3), down = -109 (0x93)
        (
            commands.step_ac_temperature(0, True),
            "55 86 0c 00 a3 00 00 00 00 00 00 00 8a",
        ),
        (
            commands.step_ac_temperature(1, False),
            "55 86 0c 01 93 00 00 00 00 00 00 00 7b",
        ),
        # setMode: buffer[4] = -127 (0x81), buffer[5] = mode
        (commands.set_ac_mode(0, 4), "55 86 0c 00 81 04 00 00 00 00 00 00 6c"),
        # setFanSpeed: buffer[4] = -126 (0x82)
        (commands.set_ac_fan(0, 2), "55 86 0c 00 82 02 00 00 00 00 00 00 6b"),
        # toggleZone(3): buffer[1] = -127 (0x81), buffer[4] = -128
        (commands.toggle_zone(3), "55 81 0c 03 80 00 00 00 00 00 00 00 65"),
        # setFan(room, +1): buffer[4] = 2, buffer[5] = 1
        (commands.step_zone(2, True), "55 81 0c 02 02 01 00 00 00 00 00 00 e7"),
        (commands.step_zone(2, False), "55 81 0c 02 01 01 00 00 00 00 00 00 e6"),
        # SetChangeTemperatureFan(room): buffer[4] = -128, buffer[5] = 1
        (
            commands.toggle_zone_control_mode(0),
            "55 81 0c 00 80 01 00 00 00 00 00 00 63",
        ),
    ],
)
def test_command_bytes(frame: bytes, expected: str) -> None:
    assert frame.hex(" ") == expected


def test_checksum_is_sum_mod_256() -> None:
    frame = commands.build(0x86, 1, 0xA3, 0xFF)
    assert len(frame) == 13
    assert frame[12] == sum(frame[:12]) % 256


def test_rejects_out_of_range_bytes() -> None:
    with pytest.raises(ValueError):
        commands.build(0x81, 256)
