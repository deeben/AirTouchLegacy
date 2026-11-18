#!/usr/bin/env python3
"""A pretend AirTouch 2 or AirTouch 3 controller.

Use it to try the integration without hardware:

    python3 tools/airtouch_sim.py --model 3            # listens on port 8899
    python3 tools/airtouch_sim.py --model 2 --port 9000

Then add the "AirTouch 2 & 3" integration in Home Assistant and point it at
the machine running this script. Every command it receives is logged, so
you can see exactly what Home Assistant sends.

The simulator deliberately does NOT reuse the integration's decoder. It
writes frames from its own copy of the byte map (taken from
docs/PROTOCOL.md), so the tests compare two independent implementations.

Only the Python standard library is needed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import logging

_LOGGER = logging.getLogger("airtouch_sim")

COMMAND_LENGTH = 13


def _text(value: str, width: int) -> bytes:
    return value.encode("ascii")[:width].ljust(width, b" ")


@dataclass
class SimZone:
    name: str
    on: bool = True
    percent: int = 50  # 0-100
    temperature_control: bool = False  # AirTouch 3 only
    setpoint: int = 22  # AirTouch 3 only
    sensor_temperature: int | None = None  # AirTouch 3 only, slot 2n
    sensor_low_battery: bool = False
    spill: bool = False
    dampers: int = 1


@dataclass
class SimAc:
    name: str
    on: bool = False
    mode: int = 4  # cool
    fan_count: int = 4  # supported speeds (high nibble)
    fan_value: int = 1  # low nibble
    setpoint: int = 22
    temperature: int = 24
    brand: int = 0
    gateway: int = 0
    error: bool = False
    error_code: int = 0


@dataclass
class Simulator:
    """Holds pretend state, applies commands and renders status frames."""

    model: int = 3
    name: str = "Simulated"
    system_id: str = "12345678"
    zones: list[SimZone] = field(default_factory=list)
    acs: list[SimAc] = field(default_factory=list)
    touchpad_temperature: int = 23
    touchpad_zone: int = 0  # AirTouch 3: 1-based zone holding the touch pad
    # Quirk switches for tests
    lag_replies: bool = False  # reply to a command with the state from before it
    corrupt_checksum: bool = False
    commands_seen: list[bytes] = field(default_factory=list)

    @classmethod
    def demo(cls, model: int) -> Simulator:
        sim = cls(model=model)
        sim.zones = [
            SimZone("Living", percent=80, sensor_temperature=24),
            SimZone("Kitchen", percent=50),
            SimZone("Master", on=False, percent=40, sensor_temperature=21),
            SimZone("Kids", percent=60, dampers=2),
        ]
        sim.acs = [SimAc("Daikin", gateway=0x08, fan_count=3, fan_value=1, brand=1)]
        if model == 3:
            sim.zones[0].temperature_control = True
            sim.zones[0].setpoint = 23
        else:
            for zone in sim.zones:
                zone.percent = round(zone.percent / 10) * 10
        return sim

    # ------------------------------------------------------------- rendering

    @property
    def step(self) -> int:
        return 5 if self.model == 3 else 10

    def frame(self) -> bytes:
        frame = self._frame_at3() if self.model == 3 else self._frame_at2()
        checksum = sum(frame[:-1]) & 0xFF
        if self.corrupt_checksum:
            checksum ^= 0xFF
        frame[-1] = checksum
        return bytes(frame)

    def _damper_layout(self) -> list[tuple[int, int]]:
        layout, start = [], 0
        for zone in self.zones:
            layout.append((start, zone.dampers))
            start += zone.dampers
        return layout

    def _frame_at3(self) -> bytearray:
        f = bytearray(492)
        f[0:2] = b"\x91\xfa"
        for i, zone in enumerate(self.zones):
            start, count = self._damper_layout()[i]
            f[104 + i * 8 : 112 + i * 8] = _text(zone.name, 8)
            for d in range(start, start + count):
                f[232 + d] = (
                    (0x80 if zone.on else 0) | (0x40 if zone.spill else 0) | (d & 7)
                )
            f[248 + i] = (0x80 if zone.temperature_control else 0) | (zone.percent // 5)
            f[264 + i] = (start << 4) | count
            source = 1 if zone.sensor_temperature is not None else 0
            f[296 + i] = (source << 5) | ((zone.setpoint - 1) & 0x1F)
            if zone.sensor_temperature is not None:
                f[451 + i * 2] = (
                    0x80
                    | (0x40 if zone.sensor_low_battery else 0)
                    | zone.sensor_temperature
                )
        f[352] = len(self.zones)
        f[383:399] = _text(self.name, 16)
        for a, ac in enumerate(self.acs):
            f[399 + a * 8 : 407 + a * 8] = _text(ac.name, 8)
            f[423 + a] = (0x80 if ac.on else 0) | (0x40 if ac.error else 0)
            f[425 + a] = ac.brand
            f[427 + a] = ac.mode
            f[429 + a] = (ac.fan_count << 4) | ac.fan_value
            f[431 + a] = ac.setpoint
            f[433 + a] = ac.temperature
            f[439 + a] = ac.gateway
        f[443] = self.touchpad_zone
        f[445] = self.touchpad_temperature
        f[483:491] = self.system_id.encode("ascii")[:8].ljust(8, b"0")
        return f

    def _frame_at2(self) -> bytearray:
        f = bytearray(395)
        f[0:2] = b"\x91\xfa"
        for i, zone in enumerate(self.zones):
            start, count = self._damper_layout()[i]
            f[100 + i * 8 : 108 + i * 8] = _text(zone.name, 8)
            for d in range(start, start + count):
                f[228 + d] = (0x80 if zone.on else 0) | (0x40 if zone.spill else 0)
                f[260 + d] = 10  # balance
                f[276 + d] = zone.percent // 10
            f[244 + i] = (start << 4) | count
        f[292] = len(self.zones)
        f[323] = self.touchpad_temperature
        f[324:340] = _text(self.name, 16)
        for a, ac in enumerate(self.acs):
            f[354 + a] = (0x80 if ac.on else 0) | (0x40 if ac.error else 0)
            f[356 + a] = ac.brand
            f[358 + a] = ac.mode
            f[360 + a] = (ac.fan_count << 4) | ac.fan_value
            f[362 + a] = ac.setpoint
            f[364 + a] = ac.temperature
            f[366 + a] = ac.error_code
            f[368 + a] = ac.gateway
            f[370 + a * 8 : 378 + a * 8] = _text(ac.name, 8)
        return f

    # -------------------------------------------------------------- commands

    def handle(self, command: bytes) -> bytes | None:
        """Apply a 13-byte command and return the reply frame (None = ignore)."""
        self.commands_seen.append(command)
        if (
            len(command) != COMMAND_LENGTH
            or command[0] != 0x55
            or command[2] != 0x0C
            or sum(command[:12]) & 0xFF != command[12]
        ):
            _LOGGER.warning("Ignoring malformed command %s", command.hex(" "))
            return None
        before = self.frame()
        kind, target, op, arg = command[1], command[3], command[4], command[5]
        if kind == 0x01:
            _LOGGER.info("status request")
        elif kind == 0x86 and target < len(self.acs):
            self._ac_command(self.acs[target], op, arg)
        elif kind == 0x81 and target < len(self.zones):
            self._zone_command(self.zones[target], op, arg)
        else:
            _LOGGER.warning("Unknown command %s", command.hex(" "))
        return before if self.lag_replies and kind != 0x01 else self.frame()

    def _ac_command(self, ac: SimAc, op: int, arg: int) -> None:
        if op == 0x80:
            ac.on = not ac.on
            _LOGGER.info("%s power -> %s", ac.name, ac.on)
        elif op == 0x81:
            ac.mode = arg
            _LOGGER.info("%s mode -> %s", ac.name, arg)
        elif op == 0x82:
            ac.fan_value = arg
            _LOGGER.info("%s fan -> %s", ac.name, arg)
        elif op in (0x93, 0xA3):
            ac.setpoint = max(16, min(30, ac.setpoint + (1 if op == 0xA3 else -1)))
            _LOGGER.info("%s set point -> %s", ac.name, ac.setpoint)

    def _zone_command(self, zone: SimZone, op: int, arg: int) -> None:
        if op == 0x80 and arg == 0:
            zone.on = not zone.on
            _LOGGER.info("%s power -> %s", zone.name, zone.on)
        elif op == 0x80 and arg == 1 and self.model == 3:
            zone.temperature_control = not zone.temperature_control
            _LOGGER.info(
                "%s temperature control -> %s", zone.name, zone.temperature_control
            )
        elif op in (0x01, 0x02) and arg == 1:
            up = op == 0x02
            if self.model == 3 and zone.temperature_control:
                zone.setpoint = max(1, min(32, zone.setpoint + (1 if up else -1)))
                _LOGGER.info("%s set point -> %s", zone.name, zone.setpoint)
            elif zone.on:
                zone.percent = max(
                    self.step,
                    min(100, zone.percent + (self.step if up else -self.step)),
                )
                _LOGGER.info("%s damper -> %s%%", zone.name, zone.percent)

    # ---------------------------------------------------------------- server

    async def serve_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                command = await reader.readexactly(COMMAND_LENGTH)
                reply = self.handle(command)
                if reply is not None:
                    writer.write(reply)
                    await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> asyncio.Server:
        return await asyncio.start_server(self.serve_client, host, port)


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", type=int, choices=(2, 3), default=3)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sim = Simulator.demo(args.model)
    server = await sim.start(args.host, args.port)
    _LOGGER.info(
        "Pretending to be an AirTouch %s on %s:%s", args.model, args.host, args.port
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())
