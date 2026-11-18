"""Diagnostics download: decoded state plus the raw status frame.

The raw frame is the most useful thing to share when something decodes
wrongly. It contains zone and system names but nothing else personal; the
host address is redacted.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import AirTouchConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AirTouchConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    state = entry.runtime_data.data
    decoded = asdict(state)
    decoded.pop("raw")
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": decoded,
        "raw_frame_hex": state.raw.hex(),
        "raw_frame_length": len(state.raw),
    }
