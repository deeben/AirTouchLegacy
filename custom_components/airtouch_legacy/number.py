"""Number entities: zone damper opening and zone target temperature.

The controller only offers "one step up / one step down" for a zone, and
what a step changes depends on the zone's control mode. So each zone gets
both numbers, and only the one that matches its current mode is available.
"""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchZoneEntity
from .protocol import Model, ZoneControl
from .protocol.client import ZONE_MAX_TEMPERATURE, ZONE_MIN_TEMPERATURE

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add damper (all models) and set point (AirTouch 3) numbers per zone."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for zone in coordinator.data.zones:
        entities.append(AirTouchDamperNumber(coordinator, zone.index))
        if coordinator.data.model is Model.AIRTOUCH3:
            entities.append(AirTouchZoneTemperatureNumber(coordinator, zone.index))
    async_add_entities(entities)


class AirTouchDamperNumber(AirTouchZoneEntity, NumberEntity):
    """How far the zone's damper is open. Setting 0% turns the zone off."""

    _attr_translation_key = "damper"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "damper")
        self._attr_native_step = self.zone.damper_step

    @property
    def available(self) -> bool:
        return super().available and self.zone.control is ZoneControl.PERCENTAGE

    @property
    def native_value(self) -> float:
        return self.zone.damper_percent

    async def async_set_native_value(self, value: float) -> None:
        client, index = self.coordinator.client, self.zone_index
        percent = round(value)
        await self.coordinator.async_run(
            lambda: client.async_set_zone_damper(index, percent)
        )


class AirTouchZoneTemperatureNumber(AirTouchZoneEntity, NumberEntity):
    """The zone's own set point, used when the zone is temperature controlled."""

    _attr_translation_key = "zone_target_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = ZONE_MIN_TEMPERATURE
    _attr_native_max_value = ZONE_MAX_TEMPERATURE
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "target_temperature")

    @property
    def available(self) -> bool:
        return super().available and self.zone.control is ZoneControl.TEMPERATURE

    @property
    def native_value(self) -> float | None:
        return self.zone.target_temperature

    async def async_set_native_value(self, value: float) -> None:
        client, index = self.coordinator.client, self.zone_index
        target = round(value)
        await self.coordinator.async_run(
            lambda: client.async_set_zone_temperature(index, target)
        )
