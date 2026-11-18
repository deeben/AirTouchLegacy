"""Select entity: switch an AirTouch 3 zone between damper % and thermostat."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchZoneEntity
from .protocol import Model, ZoneControl

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a control mode select for each AirTouch 3 zone that has a sensor."""
    coordinator = entry.runtime_data
    if coordinator.data.model is not Model.AIRTOUCH3:
        return
    async_add_entities(
        AirTouchZoneControlSelect(coordinator, zone.index)
        for zone in coordinator.data.zones
        if zone.current_temperature is not None
    )


class AirTouchZoneControlSelect(AirTouchZoneEntity, SelectEntity):
    """Percentage (fixed damper opening) or temperature (zone thermostat)."""

    _attr_translation_key = "control_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [mode.value for mode in ZoneControl]

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "control_mode")

    @property
    def current_option(self) -> str:
        return self.zone.control.value

    async def async_select_option(self, option: str) -> None:
        client, index = self.coordinator.client, self.zone_index
        control = ZoneControl(option)
        await self.coordinator.async_run(
            lambda: client.async_set_zone_control(index, control)
        )
