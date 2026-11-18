"""Config flow: ask for the controller's address, detect the model, done."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import AirTouchConfigEntry
from .protocol import (
    DEFAULT_PORT,
    AirTouchClient,
    CannotConnect,
    ProtocolError,
    SystemState,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)


async def _probe(host: str, port: int) -> tuple[SystemState | None, dict[str, str]]:
    """Read one status frame; works out the model from the reply length."""
    try:
        state = await AirTouchClient(host, port).async_get_state()
    except CannotConnect:
        return None, {"base": "cannot_connect"}
    except ProtocolError as err:
        _LOGGER.warning("Unrecognised reply from %s: %s", host, err)
        return None, {"base": "unknown_device"}
    except Exception:
        _LOGGER.exception("Unexpected error talking to %s", host)
        return None, {"base": "unknown"}
    return state, {}


def _unique_id(state: SystemState, host: str) -> str:
    """AirTouch 3 reports a device ID; AirTouch 2 does not, so use the host."""
    return state.system_id or f"{state.model}_{host}"


class AirTouchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AirTouch 2 & 3."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host, then talk to it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            self._async_abort_entries_match({CONF_HOST: host})
            state, errors = await _probe(host, port)
            if state is not None:
                await self.async_set_unique_id(_unique_id(state, host))
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PORT: port}
                )
                return self.async_create_entry(
                    title=state.name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MODEL: state.model.value,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change the address, for example after a router swap."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            state, errors = await _probe(host, port)
            if state is not None:
                if state.system_id:
                    await self.async_set_unique_id(state.system_id)
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MODEL: state.model.value,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: AirTouchConfigEntry) -> AirTouchOptionsFlow:
        """Return the options flow."""
        return AirTouchOptionsFlow()


class AirTouchOptionsFlow(OptionsFlowWithReload):
    """Let the user change how often we poll."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the poll interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
