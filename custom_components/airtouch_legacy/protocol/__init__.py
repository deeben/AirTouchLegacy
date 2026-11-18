"""Local protocol for Polyaire AirTouch 2 and AirTouch 3 controllers."""

from .client import (
    DEFAULT_PORT,
    AirTouchClient,
    AirTouchError,
    CannotConnect,
    CommandNotConfirmed,
    ProtocolError,
)
from .models import (
    AcMode,
    AcUnit,
    FanSpeed,
    Model,
    Sensor,
    SystemState,
    Zone,
    ZoneControl,
)

__all__ = [
    "DEFAULT_PORT",
    "AcMode",
    "AcUnit",
    "AirTouchClient",
    "AirTouchError",
    "CannotConnect",
    "CommandNotConfirmed",
    "FanSpeed",
    "Model",
    "ProtocolError",
    "Sensor",
    "SystemState",
    "Zone",
    "ZoneControl",
]
