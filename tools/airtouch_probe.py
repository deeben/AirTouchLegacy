#!/usr/bin/env python3
"""Read-only check against a real AirTouch 2 or 3 controller.

    python3 tools/airtouch_probe.py 192.168.1.50
    python3 tools/airtouch_probe.py 192.168.1.50 --save status.bin

It sends exactly one "request status" frame, the same harmless message the
official app sends, prints what the integration would decode, and can save
the raw reply. It never sends a control command. A saved reply is the most
useful thing to share when something decodes wrongly.

Only the Python standard library is needed (Python 3.11 or newer).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

# Import the protocol package straight from the integration folder, without
# needing Home Assistant installed.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "custom_components" / "airtouch_legacy"),
)

from protocol import AirTouchClient, AirTouchError
from protocol.client import DEFAULT_PORT


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Read-only AirTouch 2/3 status check")
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--save", type=Path, help="write the raw status frame here")
    args = parser.parse_args()

    client = AirTouchClient(args.host, args.port)
    try:
        state = await client.async_get_state()
    except AirTouchError as err:
        print(f"Failed: {err}")
        return 1

    print(f"Model:        {state.model}")
    print(f"System name:  {state.name}")
    print(f"System ID:    {state.system_id}")
    print(f"Checksum OK:  {state.checksum_ok}")
    print(f"Header:       {state.raw[:2].hex()}  (0x91fa expected)")
    print(f"Touch pad:    {state.touchpad_temperature} °C")
    for ac in state.ac_units:
        print(
            f"AC {ac.index}: {ac.name!r} power={ac.power} "
            f"mode={ac.mode.name if ac.mode is not None else None} "
            f"(raw {ac.raw_mode}) fan={ac.fan_speed} (raw 0x{ac.raw_fan:02x}, "
            f"offers {[s.value for s in ac.supported_fan_speeds]}) "
            f"set={ac.target_temperature} now={ac.current_temperature} "
            f"brand={ac.brand_id} gateway=0x{ac.gateway_id:02x} error={ac.error}"
        )
    for zone in state.zones:
        print(
            f"Zone {zone.index}: {zone.name!r} on={zone.power} "
            f"control={zone.control} damper={zone.damper_percent}% "
            f"set={zone.target_temperature} now={zone.current_temperature} "
            f"spill={zone.spill} low_battery={zone.low_battery}"
        )
    for sensor in state.sensors:
        print(
            f"Sensor slot {sensor.index}: {sensor.temperature} °C "
            f"low_battery={sensor.low_battery}"
        )
    if args.save:
        args.save.write_bytes(state.raw)
        print(f"Saved {len(state.raw)} bytes to {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
