"""Switch entity: turn each zone on or off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchZoneEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a switch for each zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        AirTouchZoneSwitch(coordinator, zone.index) for zone in coordinator.data.zones
    )


class AirTouchZoneSwitch(AirTouchZoneEntity, SwitchEntity):
    """Zone on/off. Named after the zone itself, e.g. switch.living."""

    _attr_name = None
    _attr_translation_key = "zone"

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "power")

    @property
    def is_on(self) -> bool:
        return self.zone.power

    async def async_turn_on(self, **kwargs: Any) -> None:
        client, index = self.coordinator.client, self.zone_index
        await self.coordinator.async_run(
            lambda: client.async_set_zone_power(index, True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        client, index = self.coordinator.client, self.zone_index
        await self.coordinator.async_run(
            lambda: client.async_set_zone_power(index, False)
        )
