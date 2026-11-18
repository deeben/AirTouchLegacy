"""Decoder for the AirTouch 2 status frame (395 bytes).

Offsets come from the protocol sheet in nathanvdh/airtouch2-python
(re_response/airtouch2_protocol.pdf), which was decoded from real
installations. The original AirTouch 2 has no per-zone temperature sensors:
zones are always percentage controlled, in 10% steps.
"""

from __future__ import annotations

from .common import FrameError, decode_fan, decode_text, fan_table, frame_checksum_ok
from .models import AcMode, AcUnit, Model, SystemState, Zone, ZoneControl

FRAME_LENGTH = 395

ZONE_NAMES = 100  # 16 x 8 bytes ASCII
DAMPER_STATUS = 228  # 16 dampers: bit 7 on, bit 6 spill
ZONE_DAMPERS = 244  # 16 zones: high nibble first damper, low nibble damper count
DAMPER_PERCENT = 276  # 16 dampers: 0-10 (x 10%)
ZONE_COUNT = 292
TURBO_ZONE = 297
TOUCHPAD_TEMPERATURE = 323
SYSTEM_NAME = 324  # 16 bytes ASCII
AC_STATUS = 354  # 2 bytes: bit 7 on, bit 6 error
AC_BRAND = 356  # 2 bytes: 0 none, 1 Daikin, 2 Fujitsu, ... 9 Toshiba
AC_MODE = 358
AC_FAN = 360  # high nibble speed count, low nibble speed
AC_SETPOINT = 362
AC_TEMPERATURE = 364
AC_ERROR_CODE = 366
AC_GATEWAY = 368
AC_NAMES = 370  # 2 x 8 bytes ASCII

MAX_ZONES = 16
DAMPER_STEP = 10
BRAND_DAIKIN = 1
BRAND_FUJITSU = 2


def _ac_unit(frame: bytes, index: int) -> AcUnit | None:
    status = frame[AC_STATUS + index]
    fan = frame[AC_FAN + index]
    gateway = frame[AC_GATEWAY + index]
    if fan == 0 and gateway == 0:
        return None  # AC not fitted (same rule as airtouch2-python)

    brand = frame[AC_BRAND + index]
    table = fan_table(
        fan >> 4,
        gateway,
        daikin=brand == BRAND_DAIKIN,
        fujitsu=brand == BRAND_FUJITSU,
    )
    raw_mode = frame[AC_MODE + index]
    try:
        mode: AcMode | None = AcMode(raw_mode)
    except ValueError:
        mode = None
    current = frame[AC_TEMPERATURE + index]
    name_start = AC_NAMES + index * 8

    return AcUnit(
        index=index,
        name=decode_text(frame[name_start : name_start + 8]) or f"AC {index + 1}",
        power=bool(status & 0x80),
        error=bool(status & 0x40),
        error_code=frame[AC_ERROR_CODE + index],
        mode=mode,
        fan_speed=decode_fan(fan & 0x0F, table),
        supported_fan_speeds=tuple(table),
        fan_codes=tuple(table.values()),
        target_temperature=frame[AC_SETPOINT + index],
        current_temperature=current or None,
        brand_id=brand,
        gateway_id=gateway,
        raw_mode=raw_mode,
        raw_fan=fan,
    )


def parse(frame: bytes) -> SystemState:
    """Decode an AirTouch 2 status frame."""
    if len(frame) != FRAME_LENGTH:
        raise FrameError(f"Expected {FRAME_LENGTH} bytes, got {len(frame)}")
    zone_count = frame[ZONE_COUNT]
    if zone_count > MAX_ZONES:
        raise FrameError(f"Implausible zone count {zone_count}")
    turbo_zone = frame[TURBO_ZONE]

    zones = []
    for i in range(zone_count):
        first_damper = (frame[ZONE_DAMPERS + i] >> 4) & 0x0F
        damper = frame[DAMPER_STATUS + first_damper]
        power = bool(damper & 0x80)
        name_start = ZONE_NAMES + i * 8
        zones.append(
            Zone(
                index=i,
                name=decode_text(frame[name_start : name_start + 8]) or f"Zone {i + 1}",
                power=power,
                spill=bool(damper & 0x40),
                damper_percent=(
                    min(frame[DAMPER_PERCENT + first_damper], 10) * DAMPER_STEP
                    if power
                    else 0
                ),
                damper_step=DAMPER_STEP,
                control=ZoneControl.PERCENTAGE,
                target_temperature=None,
                current_temperature=None,
                low_battery=False,
                # Turbo zone is only meaningful when turbo is active; the
                # protocol sheet notes byte 297 is 0 otherwise, which is
                # ambiguous with "zone 1", so we only expose it as a hint.
                turbo=turbo_zone == i and turbo_zone != 0,
            )
        )

    ac_units = tuple(unit for i in range(2) if (unit := _ac_unit(frame, i)) is not None)
    touchpad = frame[TOUCHPAD_TEMPERATURE]

    return SystemState(
        model=Model.AIRTOUCH2,
        name=decode_text(frame[SYSTEM_NAME : SYSTEM_NAME + 16]) or "AirTouch 2",
        system_id=None,
        ac_units=ac_units,
        zones=tuple(zones),
        sensors=(),
        touchpad_temperature=touchpad or None,
        checksum_ok=frame_checksum_ok(frame),
        raw=bytes(frame),
    )
