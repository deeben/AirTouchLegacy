# AirTouch 2 & 3 for Home Assistant

A Home Assistant custom integration for **Polyaire AirTouch 2** and
**AirTouch 3** ducted air-conditioning controllers. It talks straight to the
wall controller over your local network. There's no cloud, no add-on and no
separate API server, and nothing is collected or sent anywhere.

Home Assistant already supports AirTouch 4 and 5. AirTouch 2+ (the newer
"plus" model) is covered by
[nathanvdh/homeassistant-airtouch2](https://github.com/nathanvdh/homeassistant-airtouch2).
This integration fills the gap for the older AirTouch 2 and AirTouch 3.

> **Status: untested on real hardware.** It's built from four community
> projects that each worked on someone's system (see
> [docs/PROTOCOL.md](docs/PROTOCOL.md)), and it passes a full test suite
> against a simulated controller. The first run on a real unit should follow
> the checklist in [First run on real hardware](#first-run-on-real-hardware).

## What you get

| Device | Entities |
|---|---|
| Each air conditioner | **Climate**: on/off, Cool / Heat / Dry / Fan / Auto (`heat_cool`), fan speed, set point 16–30 °C. **Fault** sensor |
| Each zone | **Switch**: zone on/off. **Damper opening**: 0–100% (5% steps on AT3, 10% on AT2; 0% turns the zone off). **Spill** sensor |
| Each AT3 zone with a sensor | **Temperature**, **Target temperature**, **Control mode** (damper % or temperature), **Low battery** |
| The controller | **Touch pad temperature**; raw **Sensor slot N** temperatures (disabled by default) |

## Install

### With HACS

1. In HACS: ⋮ → **Custom repositories** → add
   `https://github.com/deeben/AirTouchLegacy`, type **Integration**.
2. Search HACS for **AirTouch 2 & 3 (Legacy)** and download it.
3. Restart Home Assistant.

### Manually

Copy `custom_components/airtouch_legacy` into the `custom_components` folder
of your Home Assistant config (the folder that has `configuration.yaml`), then
restart Home Assistant.

## Set up

1. Give the AirTouch a fixed IP address in the router (a DHCP reservation).
   The address is shown on the touch screen's Wi-Fi settings page.
2. **Settings → Devices & services → Add integration → AirTouch 2 & 3.**
3. Enter the IP address. Leave the port at 8899. The model is detected
   automatically.
4. Optional: **Configure** on the integration lets you change the poll
   interval (default 30 s). Changes made from the wall panel or phone app
   show up within that time. Changes made from Home Assistant show straight
   away.

If the IP address changes later, use **⋮ → Reconfigure** on the integration
to update it. You don't need to remove and re-add it.

## Try it without hardware

`tools/airtouch_sim.py` is a fake controller with four zones and one AC.
Only Python 3.11+ is needed.

```bash
python3 tools/airtouch_sim.py --model 3          # or --model 2
```

Add the integration in Home Assistant using the IP of the machine running the
simulator. Every command Home Assistant sends is logged in the terminal, so
you can see exactly what would go to a real unit.

## First run on real hardware

Do this with your friend, ideally standing next to the wall panel.

1. **Read-only check first.** From any computer on their network:

   ```bash
   python3 tools/airtouch_probe.py 192.168.x.x --save status.bin
   ```

   This sends only the "request status" message the phone app sends, and
   never a control command. Check that the zone names, AC name, on/off states,
   mode, set point and temperatures match the wall panel. Keep `status.bin`:
   it lets you decode their system offline later.
2. **Install and add the integration.** Compare the entities with the panel
   again.
3. **Try one thing at a time**, watching the wall panel:
   * turn one zone off and on,
   * move a damper by 10%,
   * change the AC set point by one degree,
   * change mode and fan speed,
   * turn the AC on and off.
4. If anything is wrong, open the AirTouch device page → **Download
   diagnostics** and send the file along with what you expected to see. It
   has the decoded state and the raw status frame, with the IP address
   removed.

Things most likely to need adjusting, in order:

* **Fan speed names** for their AC brand. The probe prints the raw fan byte
  and the speeds it thinks the AC offers.
* **Zone temperatures** if a zone shows another zone's sensor. Enable the
  "Sensor slot" entities to see raw slots.
* **Mode names** if the probe shows brand ID 11 or 15 (those brands number
  modes differently).

Turn on debug logging to see every frame sent and received:

```yaml
logger:
  logs:
    custom_components.airtouch_legacy: debug
```

## Run the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt      # Python 3.13+ for the HA tests
pytest                                    # all 70 tests
pytest tests/protocol                     # protocol only; just needs pytest + pytest-asyncio
```

## Further reading

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it's built and why
  (connection strategy, toggle safety, testing approach).
* [docs/PROTOCOL.md](docs/PROTOCOL.md): the byte-level protocol, where each
  fact came from, and where the sources disagreed.

## Credits

The protocol knowledge comes from
[L0rdCha0s/homebridge-airtouch3-airconditioner](https://github.com/L0rdCha0s/homebridge-airtouch3-airconditioner) (ISC),
[ozczecho/vzduch-dotek](https://github.com/ozczecho/vzduch-dotek) (MIT),
[tonymyatt/airtouch3api](https://github.com/tonymyatt/airtouch3api) (MIT) and
[nathanvdh/airtouch2-python](https://github.com/nathanvdh/airtouch2-python) (MIT).
This code is a fresh implementation, released under the MIT licence.
