"""The async client against the simulator: detection, idempotence, stepping."""

from __future__ import annotations

import asyncio

from airtouch_sim import Simulator
from protocol import (
    AcMode,
    AirTouchClient,
    CannotConnect,
    CommandNotConfirmed,
    FanSpeed,
    Model,
    ProtocolError,
    ZoneControl,
)
import pytest

Pair = tuple[Simulator, AirTouchClient]


def control_commands(sim: Simulator) -> list[str]:
    """Commands other than status requests, as hex strings."""
    return [c.hex(" ")[:14] for c in sim.commands_seen if c[1] != 0x01]


async def test_detects_airtouch3(at3: Pair) -> None:
    _, client = at3
    state = await client.async_get_state()
    assert client.model is Model.AIRTOUCH3
    assert [z.name for z in state.zones] == ["Living", "Kitchen", "Master", "Kids"]


async def test_detects_airtouch2(at2: Pair) -> None:
    _, client = at2
    await client.async_get_state()
    assert client.model is Model.AIRTOUCH2


async def test_power_on_sends_one_toggle_and_is_idempotent(at3: Pair) -> None:
    sim, client = at3
    state = await client.async_set_ac_power(0, True)
    assert state.ac(0).power
    await client.async_set_ac_power(0, True)  # already on: no toggle
    assert control_commands(sim) == ["55 86 0c 00 80"]


async def test_mode_and_fan(at3: Pair) -> None:
    sim, client = at3
    state = await client.async_set_ac_mode(0, AcMode.HEAT)
    assert state.ac(0).mode is AcMode.HEAT
    state = await client.async_set_ac_fan_speed(0, FanSpeed.HIGH)
    assert state.ac(0).fan_speed is FanSpeed.HIGH
    assert sim.acs[0].fan_value == 3  # Daikin: low=1, medium=2, high=3


async def test_unsupported_fan_speed(at3: Pair) -> None:
    _, client = at3
    with pytest.raises(ValueError):
        await client.async_set_ac_fan_speed(0, FanSpeed.QUIET)


async def test_ac_temperature_steps(at3: Pair) -> None:
    sim, client = at3
    state = await client.async_set_ac_temperature(0, 25)
    assert state.ac(0).target_temperature == 25
    assert control_commands(sim) == ["55 86 0c 00 a3"] * 3


async def test_ac_temperature_clamped(at3: Pair) -> None:
    _, client = at3
    state = await client.async_set_ac_temperature(0, 40)
    assert state.ac(0).target_temperature == 30


async def test_damper_steps_airtouch3(at3: Pair) -> None:
    sim, client = at3
    state = await client.async_set_zone_damper(1, 72)  # rounds to 70
    assert state.zone(1).damper_percent == 70
    assert len(control_commands(sim)) == 4  # 50 -> 70 in 5% steps


async def test_damper_steps_airtouch2(at2: Pair) -> None:
    sim, client = at2
    state = await client.async_set_zone_damper(1, 30)
    assert state.zone(1).damper_percent == 30
    assert len(control_commands(sim)) == 2  # 50 -> 30 in 10% steps


async def test_damper_on_off_zone_turns_it_on_first(at3: Pair) -> None:
    sim, client = at3
    state = await client.async_set_zone_damper(2, 50)
    assert state.zone(2).power and state.zone(2).damper_percent == 50
    assert control_commands(sim)[0] == "55 81 0c 02 80"


async def test_damper_zero_turns_zone_off(at3: Pair) -> None:
    _, client = at3
    state = await client.async_set_zone_damper(1, 0)
    assert not state.zone(1).power


async def test_damper_refused_in_temperature_mode(at3: Pair) -> None:
    sim, client = at3
    with pytest.raises(ValueError):
        await client.async_set_zone_damper(0, 60)
    assert control_commands(sim) == []


async def test_zone_set_point(at3: Pair) -> None:
    _, client = at3
    state = await client.async_set_zone_temperature(0, 20)
    assert state.zone(0).target_temperature == 20


async def test_zone_control_mode(at3: Pair) -> None:
    _, client = at3
    state = await client.async_set_zone_control(0, ZoneControl.PERCENTAGE)
    assert state.zone(0).control is ZoneControl.PERCENTAGE
    with pytest.raises(ValueError):  # Kitchen has no sensor
        await client.async_set_zone_control(1, ZoneControl.TEMPERATURE)


async def test_zone_power(at2: Pair) -> None:
    _, client = at2
    state = await client.async_set_zone_power(2, True)
    assert state.zone(2).power


async def test_lagging_replies_still_converge(at3: Pair) -> None:
    sim, client = at3
    sim.lag_replies = True
    state = await client.async_set_ac_temperature(0, 24)
    assert state.ac(0).target_temperature == 24
    assert sim.acs[0].setpoint == 24  # no overshoot
    state = await client.async_set_ac_power(0, True)
    assert state.ac(0).power


async def test_stuck_controller_raises_not_confirmed(at3: Pair) -> None:
    sim, client = at3
    sim._ac_command = lambda *args: None  # ignore every AC command
    with pytest.raises(CommandNotConfirmed) as err:
        await client.async_set_ac_power(0, True)
    assert not err.value.state.ac(0).power
    # Exactly one toggle: we never toggle twice on a guess.
    assert control_commands(sim) == ["55 86 0c 00 80"]


async def test_unsolicited_frame_is_discarded(at2: Pair) -> None:
    sim, _ = at2
    original = sim.serve_client

    async def pushy(reader, writer):  # type: ignore[no-untyped-def]
        writer.write(sim.frame())  # push a frame before anyone asks
        await original(reader, writer)

    sim.serve_client = pushy  # type: ignore[method-assign]
    server = await sim.start()
    port = server.sockets[0].getsockname()[1]
    pushy_client = AirTouchClient(
        "127.0.0.1", port, Model.AIRTOUCH2, timeout=2, step_delay=0
    )
    await asyncio.sleep(0.05)
    state = await pushy_client.async_set_zone_damper(0, 100)
    assert state.zone(0).damper_percent == 100
    server.close()
    await server.wait_closed()


async def test_cannot_connect() -> None:
    client = AirTouchClient("127.0.0.1", 1, timeout=1)
    with pytest.raises(CannotConnect):
        await client.async_get_state()


async def test_unknown_reply_length() -> None:
    async def handler(reader, writer):  # type: ignore[no-untyped-def]
        await reader.readexactly(13)
        writer.write(b"HTTP/1.0 400 Bad Request\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    with pytest.raises(ProtocolError):
        await AirTouchClient("127.0.0.1", port, timeout=1).async_get_state()
    server.close()
    await server.wait_closed()
