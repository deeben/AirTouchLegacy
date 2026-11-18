"""Plain data models for the AirTouch 2 / 3 local protocol.

Nothing in this package imports Home Assistant. That keeps the protocol code
easy to unit test, and means it could be lifted out into a PyPI library later
without changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class Model(StrEnum):
    """Which controller generation we are talking to."""

    AIRTOUCH2 = "airtouch2"
    AIRTOUCH3 = "airtouch3"


class AcMode(IntEnum):
    """Air conditioner operating mode (the values most units use on the wire)."""

    AUTO = 0
    HEAT = 1
    DRY = 2
    FAN = 3
    COOL = 4


class FanSpeed(StrEnum):
    """Fan speeds. Which ones a unit supports depends on the AC brand."""

    AUTO = "auto"
    QUIET = "quiet"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    POWERFUL = "powerful"


class ZoneControl(StrEnum):
    """How an AirTouch zone (group) is regulated.

    PERCENTAGE: the damper is held at a fixed opening (AirTouch 2 always works
    this way). TEMPERATURE: AirTouch 3 drives the damper to reach a per-zone
    set point using a wireless sensor or the touch pad.
    """

    PERCENTAGE = "percentage"
    TEMPERATURE = "temperature"


@dataclass(frozen=True, slots=True)
class AcUnit:
    """One air conditioner connected to the AirTouch (up to two)."""

    index: int
    name: str
    power: bool
    error: bool
    error_code: int | None
    mode: AcMode | None
    fan_speed: FanSpeed | None
    supported_fan_speeds: tuple[FanSpeed, ...]
    fan_codes: tuple[int, ...]  # wire value for each supported speed
    target_temperature: int
    current_temperature: int | None
    brand_id: int
    gateway_id: int
    raw_mode: int
    raw_fan: int


@dataclass(frozen=True, slots=True)
class Zone:
    """An AirTouch "group": what the wall panel and app call a zone.

    A group is made of one or more physical dampers; the controller keeps all
    dampers in a group in step, so we read the first one.
    """

    index: int
    name: str
    power: bool
    spill: bool
    damper_percent: int
    damper_step: int
    control: ZoneControl
    target_temperature: int | None
    current_temperature: int | None
    low_battery: bool
    turbo: bool = False


@dataclass(frozen=True, slots=True)
class Sensor:
    """A wireless temperature sensor slot (AirTouch 3 only)."""

    index: int
    temperature: int
    low_battery: bool


@dataclass(frozen=True, slots=True)
class SystemState:
    """Everything decoded from one status frame."""

    model: Model
    name: str
    system_id: str | None
    ac_units: tuple[AcUnit, ...]
    zones: tuple[Zone, ...]
    sensors: tuple[Sensor, ...]
    touchpad_temperature: int | None
    checksum_ok: bool
    raw: bytes = field(repr=False, compare=False)

    def ac(self, index: int) -> AcUnit:
        """Return the AC with the given index."""
        for unit in self.ac_units:
            if unit.index == index:
                return unit
        raise KeyError(f"No AC unit {index}")

    def zone(self, index: int) -> Zone:
        """Return the zone with the given index."""
        for zone in self.zones:
            if zone.index == index:
                return zone
        raise KeyError(f"No zone {index}")
