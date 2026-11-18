"""AirTouch 3 decoding, using frames built by hand from literal byte offsets.

These deliberately do not use the simulator or the decoder's own constants:
each offset here was read off the reference projects (see docs/PROTOCOL.md).
"""

from __future__ import annotations

from protocol import AcMode, FanSpeed, Model, ZoneControl, at3
from protocol.common import FrameError
import pytest


def blank() -> bytearray:
    frame = bytearray(492)
    frame[0:2] = b"\x91\xfa"
    return frame


def finish(frame: bytearray) -> bytes:
    frame[491] = sum(frame[:491]) % 256
    return bytes(frame)


def two_zone_frame() -> bytearray:
    f = blank()
    f[352] = 2  # two zones
    f[104:112] = b"Lounge  "
    f[112:120] = b"Bed\x00\x00\x00\x00\x00"
    f[264] = 0x02  # zone 0: dampers 0-1
    f[265] = 0x21  # zone 1: damper 2 only
    f[232] = 0x80  # damper 0 on
    f[233] = 0x80
    f[234] = 0x40  # damper 2 off, spill
    f[248] = 0x80 | 6  # zone 0 temperature control, 30%
    f[249] = 12  # zone 1 percentage, 60% (but off, so reads 0)
    f[296] = (1 << 5) | 21  # zone 0: sensor source 1, set point 22
    f[297] = 0
    f[451] = 0x80 | 0x40 | 25  # sensor slot 0: 25 C, low battery
    f[383:399] = b"My House".ljust(16, b" ")
    f[399:407] = b"Daikin  "
    f[423] = 0x80  # AC 0 on
    f[425] = 0  # brand
    f[427] = 4  # cool
    f[429] = (3 << 4) | 2  # 3 speeds, value 2
    f[431] = 0x80 | 23  # set point 23 (top bits ignored)
    f[433] = 26
    f[439] = 0x08  # Daikin gateway
    f[443] = 0  # no touch pad zone
    f[445] = 24
    f[483:491] = b"87654321"
    return f


def test_decodes_system() -> None:
    state = at3.parse(finish(two_zone_frame()))
    assert state.model is Model.AIRTOUCH3
    assert state.name == "My House"
    assert state.system_id == "87654321"
    assert state.touchpad_temperature == 24
    assert state.checksum_ok


def test_decodes_zones() -> None:
    lounge, bed = at3.parse(finish(two_zone_frame())).zones
    assert lounge.name == "Lounge"
    assert lounge.power and not lounge.spill
    assert lounge.control is ZoneControl.TEMPERATURE
    assert lounge.damper_percent == 30
    assert lounge.target_temperature == 22  # stored as set point - 1
    assert lounge.current_temperature == 25
    assert lounge.low_battery

    assert bed.name == "Bed"
    assert not bed.power
    assert bed.spill
    assert bed.damper_percent == 0  # off
    assert bed.control is ZoneControl.PERCENTAGE
    assert bed.current_temperature is None  # source 0 = hidden


def test_decodes_ac() -> None:
    (ac,) = at3.parse(finish(two_zone_frame())).ac_units  # AC 2 absent
    assert ac.name == "Daikin"
    assert ac.power and not ac.error
    assert ac.mode is AcMode.COOL
    assert ac.target_temperature == 23
    assert ac.current_temperature == 26
    # Daikin gateway: no Auto at 0, speeds start at 1
    assert ac.supported_fan_speeds == (FanSpeed.LOW, FanSpeed.MEDIUM, FanSpeed.HIGH)
    assert ac.fan_speed is FanSpeed.MEDIUM


def test_daikin_reports_auto_as_five() -> None:
    f = two_zone_frame()
    f[429] = (3 << 4) | 5
    assert at3.parse(finish(f)).ac_units[0].fan_speed is FanSpeed.AUTO


def test_generic_brand_fan_mapping() -> None:
    f = two_zone_frame()
    f[439] = 0x00
    f[429] = (4 << 4) | 0
    ac = at3.parse(finish(f)).ac_units[0]
    assert ac.supported_fan_speeds == (
        FanSpeed.AUTO,
        FanSpeed.LOW,
        FanSpeed.MEDIUM,
        FanSpeed.HIGH,
        FanSpeed.POWERFUL,
    )
    assert ac.fan_speed is FanSpeed.AUTO


def test_second_ac_detected() -> None:
    f = two_zone_frame()
    f[407:415] = b"Upstair "
    f[430] = 0x31
    f[440] = 0x0D
    units = at3.parse(finish(f)).ac_units
    assert [u.name for u in units] == ["Daikin", "Upstair"]


@pytest.mark.parametrize(
    ("brand", "wire", "mode"),
    [
        (11, 1, AcMode.COOL),
        (11, 2, AcMode.HEAT),
        (15, 5, AcMode.AUTO),
        (0, 1, AcMode.HEAT),
    ],
)
def test_brand_specific_modes(brand: int, wire: int, mode: AcMode) -> None:
    f = two_zone_frame()
    f[425] = brand
    f[427] = wire
    assert at3.parse(finish(f)).ac_units[0].mode is mode


def test_touchpad_zone_uses_touchpad_temperature() -> None:
    f = two_zone_frame()
    f[443] = 1  # touch pad is in zone 1 (1-based) = index 0
    f[296] = (1 << 5) | 21  # source 1 in the touch pad zone = touch pad
    assert at3.parse(finish(f)).zones[0].current_temperature == 24


def test_average_of_two_sensors() -> None:
    f = two_zone_frame()
    f[296] = (3 << 5) | 21  # average
    f[451] = 0x80 | 20
    f[452] = 0x80 | 24
    assert at3.parse(finish(f)).zones[0].current_temperature == 22


def test_second_slot_preferred_when_asked() -> None:
    f = two_zone_frame()
    f[296] = (2 << 5) | 21
    f[451] = 0x80 | 20
    f[452] = 0x80 | 24
    assert at3.parse(finish(f)).zones[0].current_temperature == 24


def test_system_id_from_nibbles() -> None:
    f = two_zone_frame()
    f[483:491] = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    assert at3.parse(finish(f)).system_id == "12345678"


def test_bad_checksum_is_reported_not_fatal() -> None:
    f = two_zone_frame()
    data = bytearray(finish(f))
    data[491] ^= 0xFF
    assert not at3.parse(bytes(data)).checksum_ok


def test_wrong_length_rejected() -> None:
    with pytest.raises(FrameError):
        at3.parse(bytes(395))


def test_implausible_zone_count_rejected() -> None:
    f = blank()
    f[352] = 40
    with pytest.raises(FrameError):
        at3.parse(finish(f))
