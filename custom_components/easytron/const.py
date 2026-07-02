"""Constants for the EASYTRON integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "easytron"
MANUFACTURER = "Stiebel Eltron"
MODEL = "EASYTRON heatapp Zentrale"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_HOST = ""
DEFAULT_USERNAME = "Expert"
DEFAULT_PASSWORD = "Expert"
DEFAULT_SCAN_INTERVAL = 120

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
VERSION_REFRESH_INTERVAL = timedelta(minutes=15)

# A device is considered "offline" if no response for this long
OFFLINE_THRESHOLD_SECONDS = 60 * 60  # 1 hour

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "climate",
    "button",
    "number",
    "switch",
    "time",
]

# Device type strings reported by dbmodules
TYPE_SENSOR = "sensor"
TYPE_THERMOSTAT = "thermostat"
TYPE_FLOOR = "floor"
TYPE_REPEATER = "repeater_bare"

# Services
SERVICE_SET_ROOM_TARGET_TEMPERATURE = "set_room_target_temperature"
SERVICE_START_INCLUSION = "start_inclusion"
SERVICE_START_EXCLUSION = "start_exclusion"
SERVICE_NETWORK_HEAL = "network_heal"
SERVICE_REMOVE_DEVICE = "remove_device"

# API paths
PATH_PING = "/api/ping"
PATH_VERSION = "/api/version"
PATH_CHALLENGE = "/api/user/token/challenge"
PATH_LOGIN = "/api/user/token/response"
PATH_DBMODULES = "/shared-gw/api/gateway/dbmodules"
PATH_ALLMODULES = "/shared-gw/api/gateway/allmodules"
PATH_SYSTEMSTATE = "/api/systemstate"
PATH_DATETIME_GET = "/admin/datetime/get"
PATH_SYSINFO_GET = "/admin/systeminformation/get"
PATH_DAYLIST = "/api/monitor/daylist"
PATH_SETLEARNMODE = "/shared-gw/api/room/setlearnmode"
PATH_POLLLEARNMODE = "/shared-gw/api/room/polllearnmode"
PATH_UPDATEDEVICE = "/shared-gw/api/gateway/updatedevice"
PATH_ADDDEVICE = "/shared-gw/api/gateway/adddevice"
PATH_REMOVEDEVICE = "/shared-gw/api/gateway/removedevice"
PATH_REORGANIZE = "/shared-gw/api/gateway/reorganize"
PATH_REBOOT = "/common/admin/system/reboot"

# Z-Way direct API (port 8083, read-only)
ZWAY_PORT = 8083

# Observed roomstatus codes from /api/room/list (read-only inference)
# Confirmed by Nathan 2026-04-21: only 42/122 rooms were "on"; 132/99 rooms were
# all on standby (99 is standby WITH an offline Z-Wave device on top).
# 132 = standby (online)
# 137 = standby (online) — variant observed 2026-07-02 with the whole house in
#       summer standby: desiredTemperature null, isComfortMode false,
#       status "ok" (every 99-room simultaneously showed status "problem")
#  99 = standby (device offline — separate `status:"problem"` field also set)
# 122 = on, manually at floor (target == minTemperature)
#  42 = on, auto schedule (day or night slot)
#  51 = on, auto schedule (legacy reference — seen historically)
ROOMSTATUS_STANDBY_CODES = frozenset({132, 137, 99})
ROOMSTATUS_ACTIVE_CODES = frozenset({42, 51, 122})
