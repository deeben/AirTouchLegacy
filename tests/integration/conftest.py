"""Fixtures for the Home Assistant tests: a simulator on a local port."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from airtouch_sim import Simulator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/airtouch_legacy."""


@pytest.fixture(autouse=True)
def fast_steps() -> Generator[None]:
    """Skip the pause between step commands."""
    with pytest.MonkeyPatch.context() as mp:
        from custom_components.airtouch_legacy.protocol import client

        original = client.AirTouchClient.__init__

        def init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["step_delay"] = 0
            original(self, *args, **kwargs)

        mp.setattr(client.AirTouchClient, "__init__", init)
        yield


@pytest.fixture(params=[3, 2], ids=["airtouch3", "airtouch2"])
async def sim(
    request: pytest.FixtureRequest, socket_enabled: None
) -> AsyncIterator[tuple[Simulator, int]]:
    """A running simulator and the port it listens on."""
    simulator = Simulator.demo(request.param)
    server = await simulator.start()
    yield simulator, server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
