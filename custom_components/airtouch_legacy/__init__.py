"""The AirTouch 2 & 3 integration.

Talks directly to a Polyaire AirTouch 2 or AirTouch 3 controller over the
local network (TCP port 8899). No cloud service, no add-on, no middleware.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL
from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .protocol import AirTouchClient, Model

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: AirTouchConfigEntry) -> bool:
    """Set up AirTouch from a config entry."""
    client = AirTouchClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        Model(entry.data[CONF_MODEL]),
    )
    coordinator = AirTouchCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AirTouchConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
