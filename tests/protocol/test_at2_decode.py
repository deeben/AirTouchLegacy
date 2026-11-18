"""AirTouch 2 decoding against the airtouch2-python protocol sheet offsets."""

from __future__ import annotations

from protocol import AcMode, FanSpeed, Model, ZoneControl, at2
from protocol.common import FrameError
import pytest


def frame() -> bytearray:
    f = bytearray(395)
    f[0:2] = b"\x91\xfa"
    f[292] = 2
    f[100:108] = b"Family  "
    f[108:116] = b"Study   "
    f[244] = 0x02  # zone 0: dampers 0-1
    f[245] = 0x21  # zone 1: damper 2
    f[228] = 0x80
    f[229] = 0x80
    f[230] = 0x00
    f[276] = 7  # 70%
    f[277] = 7
    f[278] = 4
    f[323] = 22
    f[324:340] = b"Beach House".ljust(16, b"\x00")
    f[354] = 0x80 | 0x40  # on, error
    f[356] = 2  # Fujitsu
    f[358] = 1  # heat
    f[360] = (4 << 4) | 1  # 4 speeds, value 1
    f[362] = 21
    f[364] = 19
    f[366] = 0x2A
    f[368] = 0x0D
    f[370:378] = b"Fujitsu "
    return f


def finish(f: bytearray) -> bytes:
    f[394] = sum(f[:394]) % 256
    return bytes(f)


def test_decodes_system_and_zones() -> None:
    state = at2.parse(finish(frame()))
    assert state.model is Model.AIRTOUCH2
    assert state.name == "Beach House"
    assert state.system_id is None
    assert state.touchpad_temperature == 22
    assert state.checksum_ok
    family, study = state.zones
    assert family.name == "Family" and family.power and family.damper_percent == 70
    assert family.damper_step == 10
    assert family.control is ZoneControl.PERCENTAGE
    assert family.target_temperature is None
    assert study.name == "Study" and not study.power and study.damper_percent == 0


def test_decodes_ac() -> None:
    (ac,) = at2.parse(finish(frame())).ac_units
    assert ac.name == "Fujitsu"
    assert ac.power and ac.error and ac.error_code == 0x2A
    assert ac.mode is AcMode.HEAT
    assert ac.target_temperature == 21
    assert ac.current_temperature == 19
    # Fujitsu with 4 speeds: Auto, Quiet, Low, Medium, High
    assert ac.supported_fan_speeds[:2] == (FanSpeed.AUTO, FanSpeed.QUIET)
    assert ac.fan_speed is FanSpeed.QUIET


def test_daikin_brand_byte_without_known_gateway() -> None:
    f = frame()
    f[356] = 1  # Daikin
    f[368] = 0x99  # unknown gateway
    f[360] = (3 << 4) | 1
    ac = at2.parse(finish(f)).ac_units[0]
    assert FanSpeed.AUTO not in ac.supported_fan_speeds
    assert ac.fan_speed is FanSpeed.LOW


def test_wrong_length_rejected() -> None:
    with pytest.raises(FrameError):
        at2.parse(bytes(492))
