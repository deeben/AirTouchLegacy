# How the integration is built, and why

This is written for someone who reads code comfortably but hasn't built a
Home Assistant integration before.

## The shape of it

```
Home Assistant
  │
  │  entities: climate, switch, number, select, sensor, binary_sensor
  ▼
AirTouchCoordinator        coordinator.py
  │  polls every 30 s, holds the latest SystemState, runs control commands
  ▼
AirTouchClient             protocol/client.py
  │  async TCP: connect → command → read reply → close
  ▼
at2.parse / at3.parse      protocol/at2.py, protocol/at3.py
  │  bytes → SystemState (plain dataclasses in protocol/models.py)
  ▼
AirTouch controller, TCP port 8899
```

There are two layers, and the split between them matters:

1. **`protocol/`** knows about bytes and nothing about Home Assistant. It
   decodes frames into immutable dataclasses and turns requests like "set
   the damper to 70%" into command sequences. You can run it, test it, or
   lift it into a PyPI library without Home Assistant installed. The probe
   tool (`tools/airtouch_probe.py`) does exactly that.
2. **Everything else** maps that state onto Home Assistant concepts:
   devices, entities, the config flow, translations and diagnostics.

Home Assistant's own guidelines prefer the protocol code to be a separate
PyPI package. For a private custom integration, keeping it inside the
integration folder means there's nothing extra to publish or install, and the
code needs no network access to set up. If you ever want this in Home
Assistant core, `protocol/` is already shaped to become that package.

## Key decisions

### 1. Talk to the controller directly (no middleware)

The existing AirTouch 3 option for Home Assistant (ozczecho's component) needs
the vzduch-dotek C# web API running as a separate service. Here Home
Assistant opens the TCP socket itself. That means fewer moving parts, no
extra container, and nothing outside your network. The integration sends no
data anywhere except the AirTouch controller, and stores only the host, port
and detected model in the config entry.

### 2. A short connection per operation, not a permanent socket

The Homebridge plugin keeps one socket open forever. We open a connection,
do one job (a poll, or "set the damper to 70%"), and close it.

* tonymyatt's library works this way and reports that the phone app keeps
  working alongside it. Nobody has confirmed whether the controller accepts
  more than one client at a time. If it doesn't, a permanent socket would lock
  the phone app out.
* The client never has to recover a half-broken long-lived socket: every
  operation starts clean. A bad frame only spoils that one operation.
* The cost is that changes made from the wall panel or app appear on the next
  poll (30 s by default, adjustable in the integration's options) rather than
  instantly. Changes made from Home Assistant show straight away, because
  every command returns fresh state.

An `asyncio.Lock` makes sure Home Assistant never holds two conversations at
once. If you change the zone damper and the AC mode at the same moment, they
queue.

### 3. Never toggle on a guess

The protocol only has *toggle* for on/off. If we toggled based on what we
believed the state was 30 seconds ago, and someone had pressed the wall
panel since, "turn off" would turn it **on**. So every operation:

1. reads the state fresh, on the same connection,
2. sends a toggle only if the state differs from what you asked for,
3. checks the reply, allowing one extra read in case the reply lags,
4. if it still hasn't changed, raises `CommandNotConfirmed`. It does
   **not** toggle again, since a second toggle could undo a slow first one.
   Home Assistant shows an error and the entity shows the real state.

The Homebridge plugin skips step 1 (it uses its cached state) and
airtouch3api skips steps 1 and 2 (`toggle()` really toggles).

### 4. Absolute values from step commands

Set points and damper openings can only be nudged up or down by one step.
`AirTouchClient._step_to` works out the difference, sends steps one at a
time, checks each reply, and stops with an error if the value stops moving
(for example at a hardware limit) or moves the wrong way. That handles the
"reply shows the old value" case without overshooting. vzduch-dotek's damper
loop does the same thing.

### 5. Same command, two meanings

On AirTouch 3, "zone step up" moves the **damper** when the zone is in
percentage mode and the **set point** when it's in temperature mode. So each
AirTouch 3 zone has both a "Damper opening" and a "Target temperature"
number, and only the one that matches the current mode is available. The
client also refuses the wrong one, so an automation can't silently change a
set point while trying to move a damper. Switching modes is a separate
"Control mode" select, shown only for zones that have a sensor.

### 6. Auto-detect the model

AirTouch 2 replies with 395 bytes and AirTouch 3 with 492. The config flow
sends one status request, looks at the reply length, and stores the result.
You only enter an IP address. The same check rejects AirTouch 2+, 4 and 5,
which use other protocols, with a clear message.

### 7. Entities and devices

| Device | Entities |
|---|---|
| Controller (system name) | Touch pad temperature; Sensor slot N temperature (AT3, diagnostic, disabled by default) |
| Each AC | Climate (mode, fan, set point, on/off); Fault |
| Each zone | Switch (on/off); Damper opening; Target temperature (AT3); Temperature (AT3); Control mode (AT3 with sensor); Spill; Low battery (AT3 with sensor) |

Zones are separate devices so Home Assistant suggests an area for each one,
and the entity IDs read naturally: `switch.living`,
`number.living_damper_opening`, `climate.daikin`.

AirTouch "Auto" mode maps to Home Assistant's `heat_cool`, because the AC
chooses heating or cooling to hold the set point. In Home Assistant, `auto`
means following a schedule.

### 8. Diagnostics instead of logging everything

The device page's "Download diagnostics" gives the decoded state and the raw
status frame as hex, with the IP address removed. That plus the probe tool is
how to debug your friend's system without being there: they send you the
file and you can decode it offline.

## Testing approach

Nobody here has the hardware, so the tests come at it from three directions:

* **Decoder tests** (`tests/protocol/test_at*_decode.py`) build frames byte
  by byte using offsets typed out from the reference projects, not taken from
  the decoder's own constants.
* **Command tests** (`tests/protocol/test_commands.py`) check each command
  byte for byte against what the Homebridge and C# code produce.
* **Simulator tests** run a fake controller (`tools/airtouch_sim.py`) on a
  local port. It has its own independent copy of the byte map, and quirk
  switches for lagging replies, ignored commands and unsolicited frames. The
  client tests and the full Home Assistant tests (config flow, every entity
  type, diagnostics, unload) run against it over real TCP, for both models.

The tests can't prove the reference projects were right about the hardware.
What they do prove is that this code faithfully does what those projects
documented, and that the safety logic (fresh reads, no double toggles,
bounded step loops) holds when the controller misbehaves.

## Files

```
custom_components/airtouch_legacy/
  __init__.py          setup / unload
  manifest.json        HA metadata (no external requirements)
  const.py
  config_flow.py       IP entry, auto-detect, reconfigure, options (poll interval)
  coordinator.py       polling + "run a command, publish the result"
  entity.py            base classes, device registry layout
  climate.py switch.py number.py select.py sensor.py binary_sensor.py
  diagnostics.py
  strings.json translations/en.json
  protocol/
    models.py          dataclasses and enums
    common.py          checksum, text, fan and mode tables
    commands.py        13-byte command builders
    at2.py at3.py      status frame decoders
    client.py          async TCP client and high-level operations
tools/
  airtouch_sim.py      fake controller (stdlib only)
  airtouch_probe.py    read-only check against real hardware (stdlib only)
tests/
  protocol/            no Home Assistant needed
  integration/         needs pytest-homeassistant-custom-component
```

## Possible improvements

* If the controller turns out to handle several clients happily, a
  persistent connection would let AirTouch 2's pushed frames update Home
  Assistant instantly (`local_push`).
* A climate entity per AirTouch 3 zone (instead of switch + numbers) would
  give each room a thermostat card. It's more code and more to test blind,
  so I left it for after the first real-hardware run.
* Support for a second AC's zone assignment. The protocol has a "groups per
  AC" byte on AT2 (293), but nothing confirmed for AT3.
