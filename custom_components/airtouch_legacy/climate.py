"""Climate entity: one per air conditioner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AirTouchConfigEntry, AirTouchCoordinator
from .entity import AirTouchAcEntity
from .protocol import AcMode, FanSpeed
from .protocol.client import AC_MAX_TEMPERATURE, AC_MIN_TEMPERATURE

PARALLEL_UPDATES = 1

# AirTouch "Auto" lets the AC pick heating or cooling to hold the set point,
# which is what Home Assistant calls heat_cool. (HA's "auto" means a schedule.)
MODE_TO_HVAC = {
    AcMode.AUTO: HVACMode.HEAT_COOL,
    AcMode.HEAT: HVACMode.HEAT,
    AcMode.DRY: HVACMode.DRY,
    AcMode.FAN: HVACMode.FAN_ONLY,
    AcMode.COOL: HVACMode.COOL,
}
HVAC_TO_MODE = {hvac: mode for mode, hvac in MODE_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirTouchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a climate entity for each AC."""
    coordinator = entry.runtime_data
    async_add_entities(
        AirTouchClimate(coordinator, unit.index) for unit in coordinator.data.ac_units
    )


class AirTouchClimate(AirTouchAcEntity, ClimateEntity):
    """An AirTouch-controlled air conditioner."""

    _attr_name = None
    _attr_translation_key = "ac"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
    _attr_min_temp = AC_MIN_TEMPERATURE
    _attr_max_temp = AC_MAX_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, *MODE_TO_HVAC.values()]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: AirTouchCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "climate")

    @property
    def hvac_mode(self) -> HVACMode | None:
        unit = self.unit
        if not unit.power:
            return HVACMode.OFF
        return MODE_TO_HVAC.get(unit.mode) if unit.mode is not None else None

    @property
    def fan_mode(self) -> str | None:
        speed = self.unit.fan_speed
        return speed.value if speed else None

    @property
    def fan_modes(self) -> list[str]:
        return [speed.value for speed in self.unit.supported_fan_speeds]

    @property
    def current_temperature(self) -> float | None:
        return self.unit.current_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.unit.target_temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        unit = self.unit
        attrs: dict[str, Any] = {"error": unit.error}
        if unit.error_code is not None:
            attrs["error_code"] = unit.error_code
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        index = self.ac_index
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_run(
                lambda: client.async_set_ac_power(index, False)
            )
            return
        mode = HVAC_TO_MODE[hvac_mode]
        await self.coordinator.async_run(lambda: client.async_set_ac_mode(index, mode))
        await self.coordinator.async_run(lambda: client.async_set_ac_power(index, True))

    async def async_turn_on(self) -> None:
        client, index = self.coordinator.client, self.ac_index
        await self.coordinator.async_run(lambda: client.async_set_ac_power(index, True))

    async def async_turn_off(self) -> None:
        client, index = self.coordinator.client, self.ac_index
        await self.coordinator.async_run(
            lambda: client.async_set_ac_power(index, False)
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        client, index = self.coordinator.client, self.ac_index
        speed = FanSpeed(fan_mode)
        await self.coordinator.async_run(
            lambda: client.async_set_ac_fan_speed(index, speed)
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(hvac_mode)
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            client, index = self.coordinator.client, self.ac_index
            target = round(temperature)
            await self.coordinator.async_run(
                lambda: client.async_set_ac_temperature(index, target)
            )
