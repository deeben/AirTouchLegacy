"""Builders for the 13-byte command frames.

AirTouch 2 and AirTouch 3 use the same command format:

    byte  0   0x55          fixed
    byte  1   message type  0x01 request status, 0x81 zone control, 0x86 AC control
    byte  2   0x0C          fixed
    byte  3   target        zone (group) or AC index, counted from 0
    byte  4   operation
    byte  5   argument
    bytes 6-11              zero
    byte 12   checksum      sum of bytes 0-11, modulo 256

The controller replies to every frame with a full status frame.
"""

from __future__ import annotations

from .common import checksum

HEADER = 0x55
FIXED = 0x0C

REQUEST_STATUS = 0x01
ZONE_CONTROL = 0x81
AC_CONTROL = 0x86

OP_TOGGLE = 0x80
OP_ZONE_DOWN = 0x01
OP_ZONE_UP = 0x02
OP_AC_MODE = 0x81
OP_AC_FAN = 0x82
OP_AC_TEMP_DOWN = 0x93
OP_AC_TEMP_UP = 0xA3

ARG_ZONE_POWER = 0x00
ARG_ZONE_CONTROL_MODE = 0x01
ARG_ZONE_STEP = 0x01


def build(message_type: int, target: int = 0, op: int = 0, arg: int = 0) -> bytes:
    """Build a command frame and append its checksum."""
    for value in (message_type, target, op, arg):
        if not 0 <= value <= 0xFF:
            raise ValueError(f"Command byte out of range: {value}")
    body = bytes([HEADER, message_type, FIXED, target, op, arg, 0, 0, 0, 0, 0, 0])
    return body + bytes([checksum(body)])


def request_status() -> bytes:
    """Ask for a status frame (the Homebridge plugin calls this 'init')."""
    return build(REQUEST_STATUS)


def toggle_ac(ac: int) -> bytes:
    """Toggle an AC on or off. There is no explicit 'on' or 'off' command."""
    return build(AC_CONTROL, ac, OP_TOGGLE)


def set_ac_mode(ac: int, wire_mode: int) -> bytes:
    """Set an AC's mode (already translated to the unit's wire value)."""
    return build(AC_CONTROL, ac, OP_AC_MODE, wire_mode)


def set_ac_fan(ac: int, wire_speed: int) -> bytes:
    """Set an AC's fan speed (already translated to the unit's wire value)."""
    return build(AC_CONTROL, ac, OP_AC_FAN, wire_speed)


def step_ac_temperature(ac: int, up: bool) -> bytes:
    """Nudge an AC's set point by one degree."""
    return build(AC_CONTROL, ac, OP_AC_TEMP_UP if up else OP_AC_TEMP_DOWN)


def toggle_zone(zone: int) -> bytes:
    """Toggle a zone on or off."""
    return build(ZONE_CONTROL, zone, OP_TOGGLE, ARG_ZONE_POWER)


def step_zone(zone: int, up: bool) -> bytes:
    """Nudge a zone up or down by one step.

    In percentage mode this moves the damper (5% on AirTouch 3, 10% on
    AirTouch 2). In temperature mode (AirTouch 3) it moves the zone's set
    point by one degree.
    """
    return build(ZONE_CONTROL, zone, OP_ZONE_UP if up else OP_ZONE_DOWN, ARG_ZONE_STEP)


def toggle_zone_control_mode(zone: int) -> bytes:
    """Switch an AirTouch 3 zone between percentage and temperature control."""
    return build(ZONE_CONTROL, zone, OP_TOGGLE, ARG_ZONE_CONTROL_MODE)
