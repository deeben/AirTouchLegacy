"""Config flow tests."""

from __future__ import annotations

from airtouch_sim import Simulator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.airtouch_legacy.const import CONF_SCAN_INTERVAL, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_user_flow_detects_model(
    hass: HomeAssistant, sim: tuple[Simulator, int]
) -> None:
    simulator, port = sim
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Simulated"
    assert result["data"]["model"] == f"airtouch{simulator.model}"
    expected_id = "12345678" if simulator.model == 3 else "airtouch2_127.0.0.1"
    assert result["result"].unique_id == expected_id


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass: HomeAssistant, sim: tuple[Simulator, int]) -> None:
    simulator, port = sim
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            "model": f"airtouch{simulator.model}",
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 60
