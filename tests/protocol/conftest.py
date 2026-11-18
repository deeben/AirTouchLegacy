"""Fixtures for protocol tests. These need no Home Assistant install."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "custom_components" / "airtouch_legacy"))
sys.path.insert(0, str(ROOT / "tools"))

from airtouch_sim import Simulator  # noqa: E402
from protocol import AirTouchClient  # noqa: E402


@pytest.fixture(autouse=True)
def _allow_local_sockets(request: pytest.FixtureRequest) -> None:
    """Home Assistant's test plugin blocks sockets; these tests need localhost."""
    # Without the plugin installed, sockets are already allowed.
    with suppress(pytest.FixtureLookupError):
        request.getfixturevalue("socket_enabled")


async def _serve(sim: Simulator) -> AsyncIterator[tuple[Simulator, AirTouchClient]]:
    server = await sim.start()
    port = server.sockets[0].getsockname()[1]
    client = AirTouchClient("127.0.0.1", port, timeout=2, step_delay=0)
    try:
        yield sim, client
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
async def at3() -> AsyncIterator[tuple[Simulator, AirTouchClient]]:
    """A simulated AirTouch 3 and a client pointed at it."""
    async for pair in _serve(Simulator.demo(3)):
        yield pair


@pytest.fixture
async def at2() -> AsyncIterator[tuple[Simulator, AirTouchClient]]:
    """A simulated AirTouch 2 and a client pointed at it."""
    async for pair in _serve(Simulator.demo(2)):
        yield pair
