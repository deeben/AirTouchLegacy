# AirTouch 2 / AirTouch 3 local protocol

This is what the integration speaks. Polyaire never published it. It was put
together from four community projects, which mostly agree:

| Project | Language | Covers | What it contributed |
|---|---|---|---|
| [L0rdCha0s/homebridge-airtouch3-airconditioner](https://github.com/L0rdCha0s/homebridge-airtouch3-airconditioner) | TypeScript | AT3 | The plugin you asked about. Commands, basic status, persistent socket. |
| [ozczecho/vzduch-dotek](https://github.com/ozczecho/vzduch-dotek) | C# | AT3 | Ported from the official Android app. Sensor-to-zone mapping, brand-specific mode codes, damper loop. |
| [tonymyatt/airtouch3api](https://github.com/tonymyatt/airtouch3api) | Python | AT3 | Cleanest AT3 byte map, two-AC layout, frame length 492, connect-per-request. |
| [nathanvdh/airtouch2-python](https://github.com/nathanvdh/airtouch2-python) | Python | AT2, AT2+ | Full AT2 byte map (protocol PDF), fan speed rules, gateway/brand table. |

**AirTouch 2+ is not this protocol.** It uses a newer framed protocol on port
9200, closer to AirTouch 4, and nathanvdh's integration already supports it.
AirTouch 4 and 5 are supported by Home Assistant itself.

## Transport

* TCP, port **8899**, on the controller's Wi-Fi address. No authentication.
* Home Assistant sends a 13-byte command. The controller **always replies with a
  full status frame**: 395 bytes on AirTouch 2, 492 bytes on AirTouch 3. The
  integration tells the two apart by the reply length.
* AirTouch 2 may also push a status frame unprompted when the panel is used.
* tonymyatt reports that unexpected bytes can make an AirTouch 3 stop talking,
  including to the phone app, for a couple of minutes. The integration only
  ever sends the commands below.

## Command frame (both models)

| Byte | Value |
|---|---|
| 0 | `0x55` |
| 1 | Message type: `0x01` status request, `0x81` zone control, `0x86` AC control |
| 2 | `0x0C` |
| 3 | Target: zone index or AC index, from 0 |
| 4 | Operation (below) |
| 5 | Argument |
| 6–11 | `0x00` |
| 12 | Checksum: sum of bytes 0–11, modulo 256 |

The Homebridge and C# code write these as signed bytes, so `-122` is `0x86`,
`-127` is `0x81`, `-128` is `0x80` and so on.

| Command | Type | Op (byte 4) | Arg (byte 5) | Notes |
|---|---|---|---|---|
| Request status | `0x01` | 0 | 0 | Homebridge calls it "init" |
| Toggle AC on/off | `0x86` | `0x80` | 0 | **Toggle only.** No explicit on or off |
| Set AC mode | `0x86` | `0x81` | mode | See modes below |
| Set AC fan speed | `0x86` | `0x82` | speed code | Meaning depends on brand |
| AC set point +1 °C | `0x86` | `0xA3` | 0 | |
| AC set point −1 °C | `0x86` | `0x93` | 0 | |
| Toggle zone on/off | `0x81` | `0x80` | 0 | **Toggle only** |
| Zone step up | `0x81` | `0x02` | 1 | Damper +5% (AT3) / +10% (AT2), or zone set point +1 °C if temperature controlled (AT3) |
| Zone step down | `0x81` | `0x01` | 1 | As above, downwards |
| Toggle zone control mode | `0x81` | `0x80` | 1 | AT3 only: percentage ⇄ temperature |

Nothing sets a value directly. On/off is a toggle and everything numeric is a
step. That shapes the whole client design; see ARCHITECTURE.md.

## AirTouch 3 status frame (492 bytes)

| Offset | Size | Meaning |
|---|---|---|
| 0 | 2 | Header, probably `0x91 0xFA` like AT2 (not checked) |
| 104 | 16 × 8 | Zone names, ASCII |
| 232 | 16 | Damper status: bit 7 on, bit 6 spill |
| 248 | 16 | Per zone: bit 7 = temperature control, bits 0–6 = opening ÷ 5 |
| 264 | 16 | Per zone: high nibble = first damper, low nibble = damper count |
| 296 | 16 | Per zone: bits 5–7 = temperature source, bits 0–4 = set point − 1 |
| 352 | 1 | Number of zones |
| 383 | 16 | System name, ASCII |
| 399 | 2 × 8 | AC names, ASCII |
| 423 | 2 | AC status: bit 7 on, bit 6 error |
| 425 | 2 | AC brand ID |
| 427 | 2 | AC mode (bits 0–6) |
| 429 | 2 | AC fan: high nibble = number of speeds, low nibble = speed code |
| 431 | 2 | AC set point (bits 0–5) |
| 433 | 2 | AC measured temperature |
| 439 | 2 | AC gateway ID |
| 441 | 2 | Thermostat mode (not used yet) |
| 443 | 1 | Zone the touch pad is in, counting from 1 (0 = none) |
| 445 | 1 | Touch pad temperature |
| 451 | 32 | Wireless sensors: bit 7 present, bit 6 low battery, bits 0–5 °C |
| 483 | 8 | System ID |
| 491 | 1 | Checksum, probably (sum of 0–490). Reported, not enforced |

### Zone temperature source (byte 296+n, bits 5–7)

Zone *n* owns sensor slots *2n* and *2n+1*. From vzduch-dotek's port of the
official app:

| Source | Ordinary zone | The zone holding the touch pad |
|---|---|---|
| 0 | none | none |
| 1 | slot 2n, else 2n+1 | touch pad |
| 2 | slot 2n+1, else 2n | slot 2n, else 2n+1 |
| 3 | average of both | slot 2n+1, else 2n |
| 4 | – | average of both |

The Homebridge plugin used slots *n* and *n+1* instead. That looks like a bug
that only works when zone 0 is the one with a sensor. If a zone shows the
wrong temperature on your friend's system, enable the "Sensor slot N"
diagnostic entities to see the raw slots.

## AirTouch 2 status frame (395 bytes)

From the airtouch2-python protocol sheet:

| Offset | Size | Meaning |
|---|---|---|
| 0 | 2 | Header `0x91 0xFA` |
| 2–99 | | Clock, programs and timers (ignored) |
| 100 | 16 × 8 | Zone names |
| 228 | 16 | Damper status: bit 7 on, bit 6 spill |
| 244 | 16 | Per zone: high nibble first damper, low nibble count |
| 260 | 16 | Damper balance (1–10) |
| 276 | 16 | Damper opening, 1–10 (× 10%) |
| 292 | 1 | Number of zones |
| 297 | 1 | Turbo zone |
| 299 | 1 | Turbo / safety / spill flags for both ACs |
| 323 | 1 | Touch pad temperature |
| 324 | 16 | System name |
| 354 | 2 | AC status: bit 7 on, bit 6 error, bits 0–2 program |
| 356 | 2 | Brand: 1 Daikin, 2 Fujitsu, 3 Hitachi, 4 LG, 5 Mitsubishi Electric, 6 MHI, 7 Panasonic, 8 Samsung, 9 Toshiba |
| 358 | 2 | Mode, 0–4 |
| 360 | 2 | Fan: high nibble speed count, low nibble speed code |
| 362 | 2 | Set point |
| 364 | 2 | Measured temperature |
| 366 | 2 | Error code |
| 368 | 2 | Gateway ID |
| 370 | 2 × 8 | AC names |
| 386 | 8 | Serial number |
| 394 | 1 | Checksum: sum of bytes 0–393 mod 256 |

AirTouch 2 has no zone sensors and no temperature control per zone.

## Modes

Wire values for most units: 0 Auto, 1 Heat, 2 Dry, 3 Fan, 4 Cool.

AirTouch 3 brand IDs 11 and 15 use different numbers. This comes from the
official app via vzduch-dotek and Homebridge; neither tested it on those
brands:

| Mode | Brand 11 | Brand 15 |
|---|---|---|
| Auto | 0 | 5 |
| Heat | 2 | 2 |
| Dry | 3 | 3 |
| Fan | 4 | 4 |
| Cool | 1 | 1 |

The integration applies this both when sending and when reading. If your
friend's brand ID (shown by the probe tool) is 11 or 15, check this first.

## Fan speeds

The fan byte's high nibble is how many speeds the AC has and the low nibble is
the current speed. Rules from airtouch2-python (decompiled app), which agree
with Homebridge and vzduch-dotek for the common case:

* Most brands: 0 Auto, then Low, Medium, High, Powerful from 1 upward.
* No Auto at 0 for Daikin (gateway `0x08` or AT2 brand 1), gateway `0x14`,
  or gateway `0xFF` with 3 speeds. Speeds still start at 1, and a value of 5
  or more is reported as Auto.
* Fujitsu (gateway `0x0D`/`0x22` or AT2 brand 2) with 4 speeds: 0 Auto,
  1 Quiet, 2 Low, 3 Medium, 4 High.
* Two-speed units: Low and High.
* Speed count of 0 (not reported): assume Auto, Low, Medium, High.

## Where the sources disagree

| Question | Homebridge | vzduch-dotek | airtouch3api | We use | Why |
|---|---|---|---|---|---|
| Byte 425 / 439 | brand / AC id | brand / AC id | AC id / brand ("8 = Daikin") | 425 brand, 439 gateway | AT2's gateway table maps `0x08` to Daikin, so airtouch3api's "brand 8" is the gateway ID |
| Fan value 0 | Auto | Auto | Quiet | Auto (rules above) | Three of four sources agree |
| Zone temperature | sensor *n* or *n+1* | slot *2n*/*2n+1*, by source bits | touch pad only | vzduch-dotek | Ported from the official app; 32 slots for 16 zones fits |
| AC set point | Steps every **zone** set point | AC step command | AC step command | AC step command, plus separate zone set points | Homebridge's approach changes damper openings on zones in percentage mode |
| Connection | Persistent | Persistent | Per request | Per operation | Safest for the phone app; see ARCHITECTURE.md |

## Still unknown (worth checking on real hardware)

* Whether the AT3 header is `0x91 0xFA` and byte 491 a checksum. The
  diagnostics and probe tool report both.
* Whether the AT3 reply to a step command shows the state before or after the
  step. The client handles either.
* Brand ID numbering on AT3 (it is not the AT2 1–9 list).
* Second AC: presence is detected heuristically (non-zero fan, gateway or brand).
