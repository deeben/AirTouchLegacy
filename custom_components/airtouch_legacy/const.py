"""Constants for the AirTouch 2 & 3 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "airtouch_legacy"

CONF_MODEL: Final = "model"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300

MANUFACTURER: Final = "Polyaire"
