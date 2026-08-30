# EASYTRON (Stiebel Eltron heatapp) — Home Assistant integration

A local-polling Home Assistant custom integration for the **Stiebel Eltron
EASYTRON** ("heatapp Zentrale") base station. After you sign in once, every
paired Z-Wave device on your EASYTRON — thermostats, room sensors, floor
heating actuators, and repeaters — is automatically discovered and exposed
as Home Assistant entities, along with system-level diagnostics and control
buttons.

> Works with the local web API on the EASYTRON itself (no cloud required).
> Tested against `heatapp-Software-Zentrale` firmware 2.2.x.

## Features

### Per-device entities (auto-discovered)
- Temperature sensor
- Battery percentage
- Last seen timestamp
- Z-Wave node ID
- Last radio frame age (with mesh neighbours as an attribute)
- Online / failed / interview-complete binary sensors
- Each device grouped in HA as its own *Device*

### Per-room entities
- **Climate** entity with current temperature, target temperature*, HEAT/OFF
  modes, and call-for-heat indication
- Min / max temperature numbers
- Heating active switch

### System-level / hub entities
- Controller state
- Z-Wave home ID
- Firmware version
- Total / failed / offline device counts
- Average and minimum battery levels (with the worst device as an attribute)
- Mesh size and number of nodes with mesh neighbours
- Reorganization status & last run timestamp
- Remote heat-pump-gateway IP
- System errors (count + list attribute)
- Heating active, in service mode, internet status binary sensors

### Buttons
- Reorganize Z-Wave network (heal)
- Reboot EASYTRON
- Refresh data
- Start inclusion mode (`~28s window`)
- Start exclusion mode (`~28s window`)
- Stop learn mode

### Services
- `easytron.start_inclusion` — start include mode
- `easytron.start_exclusion` — start exclude mode
- `easytron.network_heal` — trigger reorganize
- `easytron.remove_device` — remove a device from the heatapp database
  (uses the safe `removedevice` endpoint, never `markandremovedevice`)
- `easytron.set_room_target_temperature` — set a room's current target
  temperature by numeric room ID (parity with the climate entity's
  `set_temperature`, useful for automations that only know the ID)

\* See *Limitations* below for caveats around per-room *stored* day/night
configuration writes.

## Installation

### HACS (recommended)
1. In HACS go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/siperdudeuk/easytron-homeassistant` as category
   **Integration**
3. Install **EASYTRON (Stiebel Eltron heatapp)**
4. Restart Home Assistant
5. **Settings → Devices & Services → Add Integration → EASYTRON**

### Manual
1. Copy `custom_components/easytron/` into your HA `config/custom_components/`
2. Restart Home Assistant
3. Add the integration via the UI as above

## Configuration

When prompted:

| Field | Description | Default |
|------|-------------|---------|
| Host | The local IP or hostname of your EASYTRON base station | *(none — required)* |
| Username | EASYTRON expert/installer login | `Expert` |
| Password | Expert password | `Expert` |

The integration validates the connection by performing a full login + ping
before adding the entry. Once configured, all paired devices on your
EASYTRON are auto-discovered on the next coordinator refresh (no manual
device list to maintain).

## How it works

The EASYTRON base station runs a local HTTP API on port 80. The integration:

1. Performs a challenge / response login (MD5-based hash) to get a session
   token
2. Decrypts the session token using AES-256-CBC with a key derived from
   your password
3. Polls the gateway endpoints (`dbmodules`, `allmodules`, etc.) every
   30 seconds and builds Home Assistant entities for everything it finds
4. Uses the Z-Way HTTP API on port 8083 (read-only) for additional Z-Wave
   mesh and routing diagnostics

No data leaves your network. Cloud (`heatapp.de`) is never contacted.

## Limitations / known issues

### What writes work today

- **Climate `set_temperature` (current target) — works.** Routes through
  `POST /api/room/settemperature` and persists; verified end-to-end on
  firmware 2.2.39533 (Laundry target 18.0 → 18.5 → 18.0, change stable
  across coordinator refreshes).
- **`easytron.set_room_target_temperature` service — works** (as of this
  release; it now routes to the same endpoint as the climate entity).
- **Switching-times (schedule)** — read + write via
  `/api/room/switchingtimes/{get,set}`.

### What writes are NOT possible from the local API

The following per-room *stored config* values are read-only via this
integration — and as far as we can tell, they cannot be made writable
locally at all:

- **`number.<room>_day_temperature` / `_night_temperature`** — these are
  the stored day/night setpoints used by the room's schedule (distinct
  from the current target). The entities accept writes but they currently
  call `set_temperature`, which updates the *current target* and leaves
  the *stored* day/night values unchanged. Effectively misleading.
- **`number.<room>_min_temperature` / `_max_temperature`** — explicit
  stubs (log `read-only bound` warning).
- **`climate.async_set_hvac_mode`** — logs `not implemented` and no-ops.

### Why these can't be made writable

Packet capture on the same WiFi AP as both the iPhone HeatApp! app and
the EASYTRON shows that **the iPhone app only talks to the heatapp.de
cloud servers** (over HTTPS:443), even when on the same LAN. EASYTRON
maintains a persistent TLS connection to the cloud and applies these
stored-config writes via that encrypted channel — they never traverse
the local HTTP API. The local `/api/...` surface exposes only the
endpoints listed above. Adding day/night/min/max writes would require
either:

1. Reverse-engineering the EASYTRON↔heatapp.de TLS protocol and
   implementing a HA → cloud → device path (would also need the user's
   heatapp.de account credentials and would be brittle to upstream API
   changes), or
2. Upstream firmware adding the missing local endpoints, which is out
   of our control.

Until then: change day/night/min/max in the HeatApp! app on iPhone, OR
use the global Stiebel WPM-side comfort/eco setpoint and operating-mode
controls if the property uses the
[Stiebel Eltron ISG integration](https://github.com/pail23/stiebel_eltron_isg_component)
for whole-property eco/comfort schedule flips.

### Other constraints

- **Single config entry** — only one EASYTRON per HA installation is
  currently supported (multiple entries with different hosts have not
  been tested).
- **Inclusion / exclusion windows are fixed at ~28s by the Z-Wave protocol**
  and cannot be extended. The corresponding buttons fire one window each.
- The integration **never** calls `markandremovedevice` (which is
  unsafe — it removes the device from the radio as well as the heatapp
  database, and can take working devices offline). Use the
  `easytron.remove_device` service / button which uses the safe
  `removedevice` endpoint.

## Compatibility

Tested with:

- EASYTRON heatapp Software Zentrale, firmware 2.2.39533
- Z-Wave network with thermostats (radiator actuators), room sensors,
  multi-port floor heating controllers, and Aeotec Range Extender 7
  repeaters

Other Stiebel Eltron / EBV Elektronik branded heatapp gateways
(`gateway` productType rather than `zentrale`) may work but have not been
tested — the integration uses the `/shared-gw/` endpoint prefix that the
`zentrale` product requires.

## Disclaimer

This is an unofficial integration. It is not affiliated with or endorsed
by Stiebel Eltron, EBV Elektronik, or the heatapp software developers.

## License

MIT — see [LICENSE](LICENSE).
