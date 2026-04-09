# EASYTRON HA integration — build notes

## Files

```
custom_components/easytron/
  __init__.py          setup/unload + domain services
  manifest.json        HA manifest (pycryptodome dep)
  const.py             constants + endpoint paths
  api.py               async aiohttp client (port of /tmp/easytron_client.py)
  coordinator.py       DataUpdateCoordinator with EasytronData dataclass
  entity.py            base entity classes (device / system / room)
  config_flow.py       UI config flow (host/user/pass, validates by login+ping)
  sensor.py
  binary_sensor.py
  climate.py
  button.py
  number.py
  switch.py
  diagnostics.py
  services.yaml
  strings.json
  translations/en.json
hacs.json
README.md
BUILD_NOTES.md
```

## Entities created

### Per Z-Wave device (sensors, thermostats, floor ports, repeaters)

- `sensor.easytron_<device>_temperature` — °C (from dbmodules.currentTemperature)
- `sensor.easytron_<device>_battery` — %
- `sensor.easytron_<device>_last_seen` — timestamp of dbmodules.lastResponse
- `sensor.easytron_<device>_zwave_node_id` — integer node id (diagnostic)
- `sensor.easytron_<device>_last_radio_frame_age` — seconds since Z-Way
  `zway.devices[N].data.lastReceived.updateTime` (proxy for "signal freshness")
  with attributes `neighbours` / `neighbour_count` from the Z-Way mesh map
- `binary_sensor.easytron_<device>_online` — CONNECTIVITY, computed from
  lastResponse age (< 1h) and NOT isFailed
- `binary_sensor.easytron_<device>_failed` — PROBLEM, isFailed
- `binary_sensor.easytron_<device>_interview_complete` — interviewDone

### Per room (only rooms containing a thermostat or floor port get climate)

- `climate.easytron_<room>` — HEAT/OFF, current temp (room sensor preferred,
  else average of thermostats), target temp placeholder (mid of min/max),
  hvac_action HEATING when any thermostat instance has
  `heatingActive`/`calling`/`callForHeat`
- `number.easytron_room_<room>_min_temperature` — CONFIG, read + log-only write
- `number.easytron_room_<room>_max_temperature` — CONFIG, read + log-only write
- `switch.easytron_room_<room>_active` — placeholder, optimistic state, log-only

### System / hub

- `sensor.easytron_controller_state`
- `sensor.easytron_homeid`
- `sensor.easytron_firmware`
- `sensor.easytron_total_devices`
- `sensor.easytron_failed_devices`
- `sensor.easytron_offline_devices`
- `sensor.easytron_average_battery`
- `sensor.easytron_minimum_battery` — with `worst_device` attribute
- `sensor.easytron_mesh_size`
- `sensor.easytron_nodes_with_mesh_neighbours` ("mesh built" indicator)
- `sensor.easytron_network_heal_running`
- `sensor.easytron_network_heal_last_start`
- `sensor.easytron_remote_address_isg`
- `sensor.easytron_system_errors` — value = count, attribute = full errors list
- `binary_sensor.easytron_heating_active`
- `binary_sensor.easytron_in_service_mode`
- `binary_sensor.easytron_internet`
- `button.easytron_reorganize_z_wave_network`
- `button.easytron_reboot_base_station`
- `button.easytron_refresh_data`
- `button.easytron_start_z_wave_inclusion_28s`
- `button.easytron_start_z_wave_exclusion_28s`
- `button.easytron_stop_learn_mode`

## Services

- `easytron.set_room_target_temperature` (room_id, temperature) — **TODO**, logs only
- `easytron.start_inclusion` — opens ~28s include window
- `easytron.start_exclusion` — opens ~28s exclude window
- `easytron.network_heal` — triggers reorganize
- `easytron.remove_device` (device_id) — SAFE removal via
  `/shared-gw/api/gateway/removedevice` (never markandremovedevice)

## Auth + signing

Ported verbatim from `/tmp/easytron_client.py` into async `api.py`:

1. `POST /api/user/token/challenge` with `udid=web&product=stiebel-eltron`
2. `hashed = md5(password + challenge)` raw, not PBKDF2
3. `POST /api/user/token/response` — returns encrypted session devicetoken
4. AES-256-CBC decrypt with `key=SHA256(password)` and the hardcoded
   IV `D3GC5NQEFH13is04KD2tOg==`
5. Every signed call: sort params alphabetically, join as `k=v|...|`,
   append session devicetoken, md5 -> `request_signature`. Lists in the
   signature use `[v1,v2,...]`, but the POST body encodes them as
   repeated `key[]=v` to match jQuery. `reqcount` is monotonically
   incremented. `loginRejected: true` triggers an automatic re-login + retry.

## Coordinator

`DataUpdateCoordinator[EasytronData]`, 30s polling, fetches in parallel:

- dbmodules (main data source; required — raises UpdateFailed if empty)
- allmodules (room mapping; on `gateway_no_heatapp_server_connection_error`
  reuses the previously cached rooms so entities stay available during
  daemon warm-up)
- systemstate, ping, datetime/get, systeminformation/get, monitor/daylist
- version (cached for 15 min)
- Z-Way direct API (port 8083, read-only): `Object.keys(zway.devices)` implicit,
  then per-node `neighbours` and `lastReceived.updateTime` in parallel

`EasytronData` dataclass holds `devices`, `rooms`, `system`, `mesh`,
`zway_last_received`.

Z-Way is read-only — the code never issues writes to port 8083 (documented
in `api.zway_get` docstring). Only `ZWaveAPI/Run/<expr>` GETs for:
- `Object.keys(zway.devices)`
- `zway.devices[N].data.neighbours.value`
- `zway.devices[N].data.lastReceived.updateTime`

## Config flow

Single step asking host / username / password (defaults
`192.168.1.194` / `Expert` / `Expert`). Validates by doing a full login
plus `/api/ping`, aborts-if-unique based on the `uniqueid` returned by
ping so re-adding doesn't duplicate the entry.

## Diagnostics

`diagnostics.py` dumps dbmodules / allmodules / version / daylist /
systemstate with obvious PII fields redacted (remoteAddress, mac,
servicecode, sysinfo_macaddress). Credentials in the entry are also redacted.

## Known TODOs / not yet reverse-engineered

1. **Target temperature setpoint endpoint** — `climate.async_set_temperature`,
   `number.async_set_native_value` and `service set_room_target_temperature`
   all log a warning and do NOT change device state. Once the endpoint is
   known, wire them through `client.call(...)`.
2. **Per-room enable/disable** — the `switch.easytron_room_<room>_active`
   is a placeholder with optimistic local state.
3. **Per-room bound editing** — min/max temperature numbers are read-only.
   The `updatedevice` endpoint is for devices, not rooms; whichever
   `/shared-gw/api/room/...` endpoint edits the bounds has not been
   identified.
4. **markandremovedevice** — deliberately NOT exposed anywhere. It is
   dangerous (issues a Z-Wave radio remove) and requires a device reboot
   to recover from a desync. Only the SAFE `removedevice` is used.
5. **DHCP discovery** — not implemented (optional bonus from the brief).
6. **Options flow** — scan interval is fixed at 30s; could be made
   configurable via options flow later.

## Installation steps

**HACS (custom repository)**
1. HACS -> Integrations -> three-dot menu -> Custom repositories
2. Add the repo URL, category "Integration"
3. Install "EASYTRON Stiebel Eltron heatapp"
4. Restart Home Assistant
5. Settings -> Devices & Services -> Add integration -> "EASYTRON"
6. Fill host/username/password (defaults match the factory `Expert`/`Expert`)

**Manual**
1. Copy `custom_components/easytron/` into `<ha_config>/custom_components/`
2. Restart Home Assistant
3. Add via the UI as above

`pycryptodome>=3.18.0` is declared in the manifest and will be installed
automatically by HA on first setup.
