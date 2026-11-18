"""Polling coordinator: one place that owns the latest controller state."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .protocol import AirTouchClient, AirTouchError, CommandNotConfirmed, SystemState

_LOGGER = logging.getLogger(__name__)

type AirTouchConfigEntry = ConfigEntry[AirTouchCoordinator]


class AirTouchCoordinator(DataUpdateCoordinator[SystemState]):
    """Polls the controller and runs control commands.

    Every control command returns the controller's fresh state, so entities
    update straight away instead of waiting for the next poll.
    """

    config_entry: AirTouchConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: AirTouchConfigEntry, client: AirTouchClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.base_id = entry.unique_id or entry.entry_id

    async def _async_update_data(self) -> SystemState:
        try:
            state = await self.client.async_get_state()
        except AirTouchError as err:
            raise UpdateFailed(str(err)) from err
        if not state.checksum_ok:
            _LOGGER.debug("Status frame checksum mismatch; using it anyway")
        return state

    async def async_run(self, operation: Callable[[], Awaitable[SystemState]]) -> None:
        """Run a control operation and publish the state it returns."""
        try:
            state = await operation()
        except CommandNotConfirmed as err:
            # Still show what the controller actually reports.
            self.async_set_updated_data(err.state)
            raise HomeAssistantError(
                f"AirTouch did not confirm the change: {err}"
            ) from err
        except AirTouchError as err:
            raise HomeAssistantError(f"AirTouch command failed: {err}") from err
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        self.async_set_updated_data(state)
