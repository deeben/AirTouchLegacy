"""Decoder for the AirTouch 3 status frame (492 bytes).

Byte offsets were cross-checked across three independent projects:
  * L0rdCha0s/homebridge-airtouch3-airconditioner (TypeScript)
  * ozczecho/vzduch-dotek (C#, ported from the AirTouch Android app)
  * tonymyatt/airtouch3api (Python)
Where they disagree, docs/PROTOCOL.md explains which reading we chose and why.
"""

from __future__ import annotations

from .common import (
    AT3_MODE_REMAP,
    FrameError,
    decode_fan,
    decode_mode,
    decode_text,
    fan_table,
    frame_checksum_ok,
)
from .models import AcUnit, Model, Sensor, SystemState, Zone, ZoneControl

FRAME_LENGTH = 492

ZONE_NAMES = 104  # 16 x 8 bytes ASCII
DAMPER_STATUS = 232  # 16 dampers: bit 7 on, bit 6 spill
ZONE_PERCENT = 248  # 16 zones: bit 7 temperature control, bits 0-6 = percent / 5
ZONE_DAMPERS = 264  # 16 zones: high nibble first damper, low nibble damper count
ZONE_SETTING = 296  # 16 zones: bits 5-7 sensor source, bits 0-4 set point - 1
ZONE_COUNT = 352
SYSTEM_NAME = 383  # 16 bytes ASCII
AC_NAMES = 399  # 2 x 8 bytes ASCII
AC_STATUS = 423  # 2 bytes: bit 7 on, bit 6 error
AC_BRAND = 425  # 2 bytes
AC_MODE = 427  # 2 bytes
AC_FAN = 429  # 2 bytes: high nibble speed count, low nibble speed
AC_SETPOINT = 431  # 2 bytes, bits 0-5
AC_TEMPERATURE = 433  # 2 bytes
AC_GATEWAY = 439  # 2 bytes
TOUCHPAD_ZONE = 443  # 1-based zone number the touch pad sits in, 0 = none
TOUCHPAD_TEMPERATURE = 445
SENSORS = 451  # 32 sensors: bit 7 present, bit 6 low battery, bits 0-5 degrees
SYSTEM_ID = 483  # 8 bytes

MAX_ZONES = 16
MAX_SENSORS = 32
DAMPER_STEP = 5


def _sensor(frame: bytes, index: int) -> Sensor | None:
    value = frame[SENSORS + index]
    if not value & 0x80:
        return None
    return Sensor(index=index, temperature=value & 0x3F, low_battery=bool(value & 0x40))


def _zone_sensors(
    zone: int, source: int, touchpad_zone: int, sensors: dict[int, Sensor]
) -> tuple[list[Sensor], bool]:
    """Work out which sensors feed a zone's temperature.

    Returns (sensors, uses_touchpad). Each zone owns sensor slots 2n and
    2n+1. The 3-bit source field picks between them; the zone the touch pad
    sits in has an extra "touch pad" option, which shifts the numbering by
    one. This follows vzduch-dotek, which ported it from the official app.
    """
    first = sensors.get(zone * 2)
    second = sensors.get(zone * 2 + 1)

    def prefer(a: Sensor | None, b: Sensor | None) -> list[Sensor]:
        chosen = a or b
        return [chosen] if chosen else []

    both = [s for s in (first, second) if s]

    if zone == touchpad_zone - 1:
        return {
            1: ([], True),
            2: (prefer(first, second), False),
            3: (prefer(second, first), False),
            4: (both, False),
        }.get(source, ([], False))
    return {
        1: (prefer(first, second), False),
        2: (prefer(second, first), False),
        3: (both, False),
    }.get(source, ([], False))


def _ac_unit(frame: bytes, index: int) -> AcUnit | None:
    status = frame[AC_STATUS + index]
    fan = frame[AC_FAN + index]
    gateway = frame[AC_GATEWAY + index]
    brand = frame[AC_BRAND + index]
    if index > 0 and fan == 0 and gateway == 0 and brand == 0:
        return None  # second AC not fitted

    table = fan_table(fan >> 4, gateway)
    remap = AT3_MODE_REMAP.get(brand)
    raw_mode = frame[AC_MODE + index] & 0x7F
    current = frame[AC_TEMPERATURE + index]

    name_start = AC_NAMES + index * 8
    return AcUnit(
        index=index,
        name=decode_text(frame[name_start : name_start + 8]) or f"AC {index + 1}",
        power=bool(status & 0x80),
        error=bool(status & 0x40),
        error_code=None,
        mode=decode_mode(raw_mode, remap),
        fan_speed=decode_fan(fan & 0x0F, table),
        supported_fan_speeds=tuple(table),
        fan_codes=tuple(table.values()),
        target_temperature=frame[AC_SETPOINT + index] & 0x3F,
        current_temperature=current or None,
        brand_id=brand,
        gateway_id=gateway,
        raw_mode=raw_mode,
        raw_fan=fan,
    )


def _system_id(raw: bytes) -> str | None:
    if all(48 <= b <= 57 for b in raw):  # ASCII digits
        return raw.decode("ascii")
    digits = "".join(str(b & 0x0F) for b in raw)  # one digit per low nibble
    return None if set(digits) == {"0"} else digits


def parse(frame: bytes) -> SystemState:
    """Decode an AirTouch 3 status frame."""
    if len(frame) != FRAME_LENGTH:
        raise FrameError(f"Expected {FRAME_LENGTH} bytes, got {len(frame)}")
    zone_count = frame[ZONE_COUNT]
    if zone_count > MAX_ZONES:
        raise FrameError(f"Implausible zone count {zone_count}")

    sensors = {
        s.index: s for i in range(MAX_SENSORS) if (s := _sensor(frame, i)) is not None
    }
    touchpad_zone = frame[TOUCHPAD_ZONE]
    touchpad_temperature = frame[TOUCHPAD_TEMPERATURE] & 0x3F or None

    zones = []
    for i in range(zone_count):
        first_damper = (frame[ZONE_DAMPERS + i] >> 4) & 0x0F
        damper = frame[DAMPER_STATUS + first_damper]
        percent_byte = frame[ZONE_PERCENT + i]
        setting = frame[ZONE_SETTING + i]
        power = bool(damper & 0x80)

        zone_sensors, uses_touchpad = _zone_sensors(
            i, setting >> 5, touchpad_zone, sensors
        )
        if uses_touchpad:
            current = touchpad_temperature
        elif zone_sensors:
            current = round(
                sum(s.temperature for s in zone_sensors) / len(zone_sensors)
            )
        else:
            current = None

        control = (
            ZoneControl.TEMPERATURE if percent_byte & 0x80 else ZoneControl.PERCENTAGE
        )
        name_start = ZONE_NAMES + i * 8
        zones.append(
            Zone(
                index=i,
                name=decode_text(frame[name_start : name_start + 8]) or f"Zone {i + 1}",
                power=power,
                spill=bool(damper & 0x40),
                # The controller keeps the last opening while a zone is off;
                # report 0 so Home Assistant shows what the air is doing.
                damper_percent=(percent_byte & 0x7F) * DAMPER_STEP if power else 0,
                damper_step=DAMPER_STEP,
                control=control,
                target_temperature=(setting & 0x1F) + 1,
                current_temperature=current,
                low_battery=any(s.low_battery for s in zone_sensors),
            )
        )

    ac_units = tuple(unit for i in range(2) if (unit := _ac_unit(frame, i)) is not None)

    return SystemState(
        model=Model.AIRTOUCH3,
        name=decode_text(frame[SYSTEM_NAME : SYSTEM_NAME + 16]) or "AirTouch 3",
        system_id=_system_id(frame[SYSTEM_ID : SYSTEM_ID + 8]),
        ac_units=ac_units,
        zones=tuple(zones),
        sensors=tuple(sensors.values()),
        touchpad_temperature=touchpad_temperature,
        checksum_ok=frame_checksum_ok(frame),
        raw=bytes(frame),
    )
