"""End-to-end: Home Assistant entities driving the simulator over TCP."""

from __future__ import annotations

from airtouch_sim import Simulator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airtouch_legacy.const import DOMAIN
from custom_components.airtouch_legacy.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_PORT,
    SERVICE_TURN_OFF,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def setup(
    hass: HomeAssistant, simulator: Simulator, port: int
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=simulator.system_id if simulator.model == 3 else None,
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            "model": f"airtouch{simulator.model}",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_climate(hass: HomeAssistant, sim: tuple[Simulator, int]) -> None:
    simulator, port = sim
    await setup(hass, simulator, port)
    state = hass.states.get("climate.daikin")
    assert state.state == HVACMode.OFF
    assert state.attributes["fan_modes"] == ["low", "medium", "high"]
    assert state.attributes["current_temperature"] == 24

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.daikin", ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    assert simulator.acs[0].on and simulator.acs[0].mode == 1
    assert hass.states.get("climate.daikin").state == HVACMode.HEAT

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.daikin", ATTR_TEMPERATURE: 26},
        blocking=True,
    )
    assert simulator.acs[0].setpoint == 26
    assert hass.states.get("climate.daikin").attributes[ATTR_TEMPERATURE] == 26

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_FAN_MODE,
        {ATTR_ENTITY_ID: "climate.daikin", ATTR_FAN_MODE: "high"},
        blocking=True,
    )
    assert simulator.acs[0].fan_value == 3

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.daikin", ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    assert not simulator.acs[0].on


async def test_zone_switch_and_damper(
    hass: HomeAssistant, sim: tuple[Simulator, int]
) -> None:
    simulator, port = sim
    await setup(hass, simulator, port)
    assert hass.states.get("switch.kitchen").state == STATE_ON
    assert hass.states.get("switch.master").state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.kitchen"},
        blocking=True,
    )
    assert not simulator.zones[1].on

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.kitchen_damper_opening", "value": 80},
        blocking=True,
    )
    assert simulator.zones[1].on and simulator.zones[1].percent == 80
    assert hass.states.get("number.kitchen_damper_opening").state == "80"


async def test_airtouch3_zone_temperature(
    hass: HomeAssistant, sim: tuple[Simulator, int]
) -> None:
    simulator, port = sim
    if simulator.model != 3:
        pytest.skip("AirTouch 3 only")
    await setup(hass, simulator, port)
    # Living is temperature controlled: damper is unavailable, set point is not
    assert hass.states.get("number.living_damper_opening").state == STATE_UNAVAILABLE
    assert hass.states.get("number.living_target_temperature").state == "23"
    assert hass.states.get("sensor.living_temperature").state == "24"
    assert hass.states.get("select.living_control_mode").state == "temperature"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.living_target_temperature", "value": 21},
        blocking=True,
    )
    assert simulator.zones[0].setpoint == 21

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.living_control_mode", "option": "percentage"},
        blocking=True,
    )
    assert not simulator.zones[0].temperature_control
    assert hass.states.get("number.living_damper_opening").state == "80"


async def test_unconfirmed_command_raises(
    hass: HomeAssistant, sim: tuple[Simulator, int]
) -> None:
    simulator, port = sim
    await setup(hass, simulator, port)
    simulator._zone_command = lambda *args: None  # controller ignores zones
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.kitchen"},
            blocking=True,
        )
    assert hass.states.get("switch.kitchen").state == STATE_ON


async def test_diagnostics(hass: HomeAssistant, sim: tuple[Simulator, int]) -> None:
    simulator, port = sim
    entry = await setup(hass, simulator, port)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"][CONF_HOST] == "**REDACTED**"
    assert diagnostics["raw_frame_length"] == (492 if simulator.model == 3 else 395)
    assert diagnostics["state"]["name"] == "Simulated"


async def test_unload(hass: HomeAssistant, sim: tuple[Simulator, int]) -> None:
    simulator, port = sim
    entry = await setup(hass, simulator, port)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
