"""Async TCP client for AirTouch 2 and AirTouch 3 controllers.

Design notes (more in docs/ARCHITECTURE.md):

* One short-lived TCP connection per operation. A status poll is connect,
  send one frame, read one frame, close. tonymyatt/airtouch3api uses this
  pattern and reports it does not disturb the official app. Keeping a socket
  open permanently, as the Homebridge plugin does, risks locking the app out
  if the controller only accepts one client at a time.
* Operations are serialised with a lock, so Home Assistant never has two
  conversations with the controller at once.
* The protocol has no "set to X" commands for on/off, set point or damper.
  It only has "toggle" and "one step up/down". So every high-level call
  reads fresh state first, sends the fewest commands needed, and checks each
  reply. A toggle is never sent based on stale state.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
import logging

from . import at2, at3, commands
from .common import AT3_MODE_REMAP, FrameError, encode_mode
from .models import AcMode, FanSpeed, Model, SystemState, ZoneControl

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8899

FRAME_LENGTHS = {Model.AIRTOUCH2: at2.FRAME_LENGTH, Model.AIRTOUCH3: at3.FRAME_LENGTH}
PARSERS: dict[Model, Callable[[bytes], SystemState]] = {
    Model.AIRTOUCH2: at2.parse,
    Model.AIRTOUCH3: at3.parse,
}

AC_MIN_TEMPERATURE = 16
AC_MAX_TEMPERATURE = 30
ZONE_MIN_TEMPERATURE = 15
ZONE_MAX_TEMPERATURE = 30


class AirTouchError(Exception):
    """Base class for client errors."""


class CannotConnect(AirTouchError):
    """The controller could not be reached or stopped talking."""


class ProtocolError(AirTouchError):
    """The controller sent something we could not understand."""


class CommandNotConfirmed(AirTouchError):
    """A command was sent but the controller's state did not change as expected.

    `state` is the latest state read, so callers can still show the truth.
    """

    def __init__(self, message: str, state: SystemState) -> None:
        super().__init__(message)
        self.state = state


def model_for_length(length: int) -> Model | None:
    """Identify the controller from the length of a status reply."""
    for model, frame_length in FRAME_LENGTHS.items():
        if length and length % frame_length == 0:
            return model
    return None


class _Session:
    """One open connection, used for a single high-level operation."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        model: Model,
        timeout: float,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self.model = model
        self._timeout = timeout

    async def _discard_pending(self) -> None:
        """Drop anything the controller sent unprompted before our command.

        AirTouch 2 can push a status frame when someone uses the wall panel.
        Reading it here keeps our reply aligned with our command.
        """
        while True:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), 0.01)
            except TimeoutError:
                return
            if not chunk:
                return
            _LOGGER.debug("Discarded %d unsolicited bytes", len(chunk))

    async def exchange(self, frame: bytes) -> SystemState:
        """Send one command frame and decode the status frame sent back."""
        await self._discard_pending()
        _LOGGER.debug("Sending %s", frame.hex(" "))
        self._writer.write(frame)
        await self._writer.drain()
        data = await asyncio.wait_for(
            self._reader.readexactly(FRAME_LENGTHS[self.model]), self._timeout
        )
        try:
            return PARSERS[self.model](data)
        except FrameError as err:
            raise ProtocolError(str(err)) from err

    async def status(self) -> SystemState:
        """Request and decode a status frame."""
        return await self.exchange(commands.request_status())


class AirTouchClient:
    """Talks to one AirTouch 2 or AirTouch 3 controller."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        model: Model | None = None,
        *,
        timeout: float = 10.0,
        step_delay: float = 0.4,
    ) -> None:
        self.host = host
        self.port = port
        self.model = model
        self._timeout = timeout
        self._step_delay = step_delay
        self._lock = asyncio.Lock()

    # ----------------------------------------------------------------- plumbing

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[_Session]:
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), self._timeout
                )
            except (OSError, TimeoutError) as err:
                raise CannotConnect(
                    f"Cannot connect to {self.host}:{self.port}: {err}"
                ) from err
            try:
                if self.model is None:
                    self.model = await self._detect_model(reader, writer)
                yield _Session(reader, writer, self.model, self._timeout)
            except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
                raise CannotConnect(f"Lost connection to {self.host}: {err!r}") from err
            finally:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

    async def _detect_model(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> Model:
        """Send a status request and work out the model from the reply length.

        AirTouch 2 replies with 395 bytes and AirTouch 3 with 492, so we read
        until the controller goes quiet and look at what we got.
        """
        writer.write(commands.request_status())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), self._timeout)
        while data and len(data) < max(FRAME_LENGTHS.values()):
            try:
                chunk = await asyncio.wait_for(reader.read(4096), 1.0)
            except TimeoutError:
                break
            if not chunk:
                break
            data += chunk
        model = model_for_length(len(data))
        if model is None:
            raise ProtocolError(
                f"Unrecognised reply length {len(data)} bytes; expected "
                f"{at2.FRAME_LENGTH} (AirTouch 2) or {at3.FRAME_LENGTH} (AirTouch 3)"
            )
        _LOGGER.debug("Detected %s from a %d byte reply", model, len(data))
        return model

    async def _confirm(
        self,
        session: _Session,
        state: SystemState,
        check: Callable[[SystemState], bool],
        what: str,
    ) -> SystemState:
        """Return state once `check` passes, allowing one re-read for lag."""
        if check(state):
            return state
        await asyncio.sleep(self._step_delay)
        state = await session.status()
        if check(state):
            return state
        raise CommandNotConfirmed(f"Controller did not confirm: {what}", state)

    async def _step_to(
        self,
        session: _Session,
        state: SystemState,
        read: Callable[[SystemState], int | None],
        step: Callable[[bool], bytes],
        target: int,
        what: str,
        max_steps: int = 25,
    ) -> SystemState:
        """Send up/down steps until `read(state)` reaches `target`."""
        current = read(state)
        for _ in range(max_steps):
            if current is None or current == target:
                return state
            up = target > current
            state = await session.exchange(step(up))
            new = read(state)
            if new == current:
                # The reply may predate the change; look once more.
                await asyncio.sleep(self._step_delay)
                state = await session.status()
                new = read(state)
            if new is None or new == current or (new > current) != up:
                raise CommandNotConfirmed(
                    f"{what} stopped at {new} while heading for {target}", state
                )
            current = new
            await asyncio.sleep(self._step_delay)
        if current != target:
            raise CommandNotConfirmed(f"{what} did not reach {target}", state)
        return state

    # ------------------------------------------------------------------ reading

    async def async_get_state(self) -> SystemState:
        """Read the current state of the whole system."""
        async with self._session() as session:
            return await session.status()

    # --------------------------------------------------------------- AC control

    async def async_set_ac_power(self, ac: int, on: bool) -> SystemState:
        """Turn an AC on or off (toggles only if needed)."""
        async with self._session() as session:
            state = await session.status()
            if state.ac(ac).power == on:
                return state
            state = await session.exchange(commands.toggle_ac(ac))
            return await self._confirm(
                session, state, lambda s: s.ac(ac).power == on, f"AC {ac} power {on}"
            )

    async def async_set_ac_mode(self, ac: int, mode: AcMode) -> SystemState:
        """Set an AC's mode."""
        async with self._session() as session:
            state = await session.status()
            unit = state.ac(ac)
            if unit.mode == mode:
                return state
            remap = (
                AT3_MODE_REMAP.get(unit.brand_id)
                if state.model is Model.AIRTOUCH3
                else None
            )
            state = await session.exchange(
                commands.set_ac_mode(ac, encode_mode(mode, remap))
            )
            return await self._confirm(
                session, state, lambda s: s.ac(ac).mode == mode, f"AC {ac} mode {mode}"
            )

    async def async_set_ac_fan_speed(self, ac: int, speed: FanSpeed) -> SystemState:
        """Set an AC's fan speed."""
        async with self._session() as session:
            state = await session.status()
            unit = state.ac(ac)
            if unit.fan_speed == speed:
                return state
            if speed not in unit.supported_fan_speeds:
                raise ValueError(f"{unit.name} does not support fan speed {speed}")
            code = unit.fan_codes[unit.supported_fan_speeds.index(speed)]
            state = await session.exchange(commands.set_ac_fan(ac, code))
            return await self._confirm(
                session,
                state,
                lambda s: s.ac(ac).fan_speed == speed,
                f"AC {ac} fan {speed}",
            )

    async def async_set_ac_temperature(
        self, ac: int, temperature: float
    ) -> SystemState:
        """Set an AC's set point, one degree at a time."""
        target = max(AC_MIN_TEMPERATURE, min(AC_MAX_TEMPERATURE, round(temperature)))
        async with self._session() as session:
            state = await session.status()
            return await self._step_to(
                session,
                state,
                lambda s: s.ac(ac).target_temperature,
                lambda up: commands.step_ac_temperature(ac, up),
                target,
                f"AC {ac} set point",
            )

    # ------------------------------------------------------------- zone control

    async def async_set_zone_power(self, zone: int, on: bool) -> SystemState:
        """Turn a zone on or off (toggles only if needed)."""
        async with self._session() as session:
            state = await session.status()
            return await self._zone_power(session, state, zone, on)

    async def _zone_power(
        self, session: _Session, state: SystemState, zone: int, on: bool
    ) -> SystemState:
        if state.zone(zone).power == on:
            return state
        state = await session.exchange(commands.toggle_zone(zone))
        return await self._confirm(
            session,
            state,
            lambda s: s.zone(zone).power == on,
            f"zone {zone} power {on}",
        )

    async def async_set_zone_damper(self, zone: int, percent: int) -> SystemState:
        """Set a percentage-controlled zone's damper opening.

        0% turns the zone off, matching the wall panel's behaviour.
        """
        async with self._session() as session:
            state = await session.status()
            current = state.zone(zone)
            if current.control is not ZoneControl.PERCENTAGE:
                raise ValueError(
                    f"Zone {current.name} is temperature controlled; set its "
                    "target temperature instead"
                )
            step = current.damper_step
            target = max(0, min(100, step * round(percent / step)))
            if target == 0:
                return await self._zone_power(session, state, zone, False)
            state = await self._zone_power(session, state, zone, True)
            return await self._step_to(
                session,
                state,
                lambda s: s.zone(zone).damper_percent,
                lambda up: commands.step_zone(zone, up),
                target,
                f"zone {zone} damper",
                max_steps=100 // step + 1,
            )

    async def async_set_zone_temperature(
        self, zone: int, temperature: float
    ) -> SystemState:
        """Set a temperature-controlled zone's set point (AirTouch 3 only)."""
        target = max(
            ZONE_MIN_TEMPERATURE, min(ZONE_MAX_TEMPERATURE, round(temperature))
        )
        async with self._session() as session:
            state = await session.status()
            current = state.zone(zone)
            if current.control is not ZoneControl.TEMPERATURE:
                raise ValueError(
                    f"Zone {current.name} is percentage controlled; set its "
                    "damper opening instead"
                )
            return await self._step_to(
                session,
                state,
                lambda s: s.zone(zone).target_temperature,
                lambda up: commands.step_zone(zone, up),
                target,
                f"zone {zone} set point",
            )

    async def async_set_zone_control(
        self, zone: int, control: ZoneControl
    ) -> SystemState:
        """Switch an AirTouch 3 zone between percentage and temperature control."""
        async with self._session() as session:
            state = await session.status()
            if state.model is not Model.AIRTOUCH3:
                raise ValueError("Only AirTouch 3 zones have a control mode")
            current = state.zone(zone)
            if current.control is control:
                return state
            if (
                control is ZoneControl.TEMPERATURE
                and current.current_temperature is None
            ):
                raise ValueError(f"Zone {current.name} has no temperature sensor")
            state = await session.exchange(commands.toggle_zone_control_mode(zone))
            return await self._confirm(
                session,
                state,
                lambda s: s.zone(zone).control is control,
                f"zone {zone} control {control}",
            )
