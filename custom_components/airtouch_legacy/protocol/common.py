"""Helpers shared by the AirTouch 2 and AirTouch 3 decoders."""

from __future__ import annotations

from .models import AcMode, FanSpeed


class FrameError(ValueError):
    """The bytes received do not look like a status frame."""


# Both generations start their status frame with these two bytes (documented
# for AirTouch 2; assumed for AirTouch 3, which shares the command format).
STATUS_HEADER = b"\x91\xfa"

# Gateway IDs that identify the AC brand more reliably than the brand byte.
# Collected by the airtouch2-python project from real installations.
GATEWAY_DAIKIN = frozenset({0x08})
GATEWAY_FUJITSU = frozenset({0x0D, 0x22})


def checksum(data: bytes) -> int:
    """Return the AirTouch checksum: the sum of all bytes, modulo 256."""
    return sum(data) & 0xFF


def frame_checksum_ok(frame: bytes) -> bool:
    """True when the last byte of a status frame is the checksum of the rest."""
    return len(frame) > 1 and checksum(frame[:-1]) == frame[-1]


def decode_text(raw: bytes) -> str:
    """Decode a fixed-width, space or NUL padded ASCII field."""
    text = raw.split(b"\x00", 1)[0].decode("latin-1")
    return "".join(ch for ch in text if ch.isprintable()).strip()


def fan_table(
    speed_count: int,
    gateway_id: int,
    *,
    daikin: bool = False,
    fujitsu: bool = False,
) -> dict[FanSpeed, int]:
    """Return the fan speeds this AC offers, mapped to their wire values.

    The fan byte's top nibble is the number of speeds the AC supports and the
    bottom nibble is the current speed. What each value means depends on the
    brand. These rules come from the decompiled AirTouch app via
    airtouch2-python, and agree with the Homebridge plugin and vzduch-dotek
    for the common 0=Auto, 1=Low, 2=Medium, 3=High case.
    """
    daikin = daikin or gateway_id in GATEWAY_DAIKIN
    fujitsu = fujitsu or gateway_id in GATEWAY_FUJITSU

    if speed_count == 0:
        # Speed count not reported: fall back to the most common layout.
        return {
            FanSpeed.AUTO: 0,
            FanSpeed.LOW: 1,
            FanSpeed.MEDIUM: 2,
            FanSpeed.HIGH: 3,
        }

    if fujitsu and speed_count == 4:
        return {
            FanSpeed.AUTO: 0,
            FanSpeed.QUIET: 1,
            FanSpeed.LOW: 2,
            FanSpeed.MEDIUM: 3,
            FanSpeed.HIGH: 4,
        }

    if speed_count == 2:
        speeds = [FanSpeed.LOW, FanSpeed.HIGH]
    elif speed_count == 1:
        speeds = [FanSpeed.LOW]
    else:
        speeds = [FanSpeed.LOW, FanSpeed.MEDIUM, FanSpeed.HIGH, FanSpeed.POWERFUL][
            :speed_count
        ]

    has_auto = not (
        daikin or gateway_id == 0x14 or (gateway_id == 0xFF and speed_count == 3)
    )
    # Speeds always start at 1; units with Auto use 0 for it.
    table = {speed: i + 1 for i, speed in enumerate(speeds)}
    if has_auto:
        table = {FanSpeed.AUTO: 0, **table}
    return table


def decode_fan(value: int, table: dict[FanSpeed, int]) -> FanSpeed | None:
    """Translate a wire fan value into a FanSpeed."""
    for speed, wire in table.items():
        if wire == value:
            return speed
    # Values of 5 and above mean Auto (Daikin units report Auto this way).
    if value >= 5:
        return FanSpeed.AUTO
    return None


# Some AirTouch 3 brand IDs number the modes differently. These tables come
# from the original AirTouch Android app, as carried into both the Homebridge
# plugin and vzduch-dotek. Neither project tested them on these brands.
AT3_MODE_REMAP: dict[int, dict[AcMode, int]] = {
    11: {
        AcMode.AUTO: 0,
        AcMode.HEAT: 2,
        AcMode.DRY: 3,
        AcMode.FAN: 4,
        AcMode.COOL: 1,
    },
    15: {
        AcMode.AUTO: 5,
        AcMode.HEAT: 2,
        AcMode.DRY: 3,
        AcMode.FAN: 4,
        AcMode.COOL: 1,
    },
}


def encode_mode(mode: AcMode, remap: dict[AcMode, int] | None) -> int:
    """Translate an AcMode into the wire value for this unit."""
    return remap[mode] if remap else int(mode)


def decode_mode(value: int, remap: dict[AcMode, int] | None) -> AcMode | None:
    """Translate a wire mode value into an AcMode."""
    if remap:
        for mode, wire in remap.items():
            if wire == value:
                return mode
        return None
    try:
        return AcMode(value)
    except ValueError:
        return None
