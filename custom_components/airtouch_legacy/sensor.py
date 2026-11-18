"""Temperature sensors: zones, touch pad and raw wireless sensor slots."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchEntity, AirTouchZoneEntity
from .protocol import Model

PARALLEL_UPDATES = 0

SENSOR_SLOTS = 32


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add temperature sensors."""
    coordinator = entry.runtime_data
    state = coordinator.data
    entities: list[SensorEntity] = [AirTouchTouchpadTemperature(coordinator)]
    if state.model is Model.AIRTOUCH3:
        entities.extend(
            AirTouchZoneTemperature(coordinator, zone.index) for zone in state.zones
        )
        entities.extend(
            AirTouchSensorSlot(coordinator, slot)
            for slot in range(SENSOR_SLOTS)
            if any(s.index == slot for s in state.sensors)
        )
    async_add_entities(entities)


class _TemperatureMixin:
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


class AirTouchTouchpadTemperature(_TemperatureMixin, AirTouchEntity, SensorEntity):
    """Temperature measured by the wall touch pad."""

    _attr_translation_key = "touchpad_temperature"

    def __init__(self, coordinator: AirTouchCoordinator) -> None:
        super().__init__(coordinator, "touchpad_temperature")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.touchpad_temperature


class AirTouchZoneTemperature(_TemperatureMixin, AirTouchZoneEntity, SensorEntity):
    """The temperature the controller uses for this zone (AirTouch 3)."""

    _attr_translation_key = "zone_temperature"

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "temperature")

    @property
    def available(self) -> bool:
        return super().available and self.zone.current_temperature is not None

    @property
    def native_value(self) -> int | None:
        return self.zone.current_temperature


class AirTouchSensorSlot(_TemperatureMixin, AirTouchEntity, SensorEntity):
    """A raw wireless sensor slot, for checking the zone/sensor mapping.

    Disabled by default; the zone temperature sensors are what most people
    want. Enable these if a zone shows the wrong temperature.
    """

    _attr_translation_key = "sensor_slot"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: AirTouchCoordinator, slot: int) -> None:
        super().__init__(coordinator, f"sensor_slot_{slot}")
        self._slot = slot
        self._attr_translation_placeholders = {"slot": str(slot + 1)}

    @property
    def available(self) -> bool:
        return super().available and any(
            s.index == self._slot for s in self.coordinator.data.sensors
        )

    @property
    def native_value(self) -> int | None:
        for sensor in self.coordinator.data.sensors:
            if sensor.index == self._slot:
                return sensor.temperature
        return None
