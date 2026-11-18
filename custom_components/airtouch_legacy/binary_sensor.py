"""Binary sensors: AC fault, zone spill and sensor battery."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchAcEntity, AirTouchZoneEntity
from .protocol import Model

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add binary sensors."""
    coordinator = entry.runtime_data
    state = coordinator.data
    entities: list[BinarySensorEntity] = [
        AirTouchAcError(coordinator, unit.index) for unit in state.ac_units
    ]
    for zone in state.zones:
        entities.append(AirTouchZoneSpill(coordinator, zone.index))
        if state.model is Model.AIRTOUCH3 and zone.current_temperature is not None:
            entities.append(AirTouchZoneLowBattery(coordinator, zone.index))
    async_add_entities(entities)


class AirTouchAcError(AirTouchAcEntity, BinarySensorEntity):
    """On when the AC reports a fault."""

    _attr_translation_key = "ac_error"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "error")

    @property
    def is_on(self) -> bool:
        return self.unit.error


class AirTouchZoneSpill(AirTouchZoneEntity, BinarySensorEntity):
    """On when the controller is dumping excess air into this zone."""

    _attr_translation_key = "spill"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "spill")

    @property
    def is_on(self) -> bool:
        return self.zone.spill


class AirTouchZoneLowBattery(AirTouchZoneEntity, BinarySensorEntity):
    """On when the zone's wireless sensor battery is low."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "low_battery")

    @property
    def is_on(self) -> bool:
        return self.zone.low_battery
