"""Data update coordinator for EASYTRON."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EasytronApiError, EasytronAuthError, EasytronClient
from .const import (
    DOMAIN,
    OFFLINE_THRESHOLD_SECONDS,
    TYPE_FLOOR,
    TYPE_SENSOR,
    TYPE_THERMOSTAT,
    UPDATE_INTERVAL,
    VERSION_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceState:
    """State of a single paired Z-Wave device (radiator, sensor, floor, repeater)."""

    id: str
    name: str
    room: str
    room_id: int | None
    node_id: int | None
    type: str
    current_temperature: float | None
    battery: int | None
    is_failed: bool
    last_response: int | None
    interview_done: bool
    vendor_id: Any
    product_id: Any
    instances: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_online(self) -> bool:
        if self.is_failed:
            return False
        if self.last_response is None:
            return True
        age = datetime.now(tz=timezone.utc).timestamp() - self.last_response
        return age < OFFLINE_THRESHOLD_SECONDS


@dataclass
class RoomState:
    id: int
    name: str
    min_temperature: float | None
    max_temperature: float | None
    desired_temperature: float | None = None
    desired_temp_day: float | None = None
    desired_temp_night: float | None = None
    actual_temperature: float | None = None
    is_comfort_mode: bool | None = None
    window_open: bool | None = None
    cooling: bool = False
    schedule: list[Any] = field(default_factory=list)
    device_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemState:
    controller_state: Any = None
    home_id: Any = None
    firmware: str | None = None
    server_version: str | None = None
    uniqueid: str | None = None
    remote_address: str | None = None
    name: str | None = None
    location: str | None = None
    errors: list[Any] = field(default_factory=list)
    reorganization_running: bool = False
    reorganization_start_time: int | None = None
    reorganization_duration: int | None = None
    current_time: int | None = None
    internet: bool | None = None
    on_maintenance: bool = False
    daylist: list[str] = field(default_factory=list)


@dataclass
class EasytronData:
    devices: dict[str, DeviceState] = field(default_factory=dict)
    rooms: dict[int, RoomState] = field(default_factory=dict)
    system: SystemState = field(default_factory=SystemState)
    mesh: dict[int, list[int]] = field(default_factory=dict)
    zway_last_received: dict[int, float] = field(default_factory=dict)


class EasytronCoordinator(DataUpdateCoordinator[EasytronData]):
    """Coordinator that polls all EASYTRON endpoints in parallel."""

    def __init__(self, hass: HomeAssistant, client: EasytronClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client.host}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._version_cached: dict[str, Any] | None = None
        self._version_last: datetime | None = None
        self._last_allmodules: dict[str, Any] | None = None
        self._last_rooms: dict[int, RoomState] = {}
        self._zway_last: datetime | None = None
        self._zway_interval = timedelta(minutes=5)
        self._schedule_last: datetime | None = None
        self._schedule_interval = timedelta(minutes=5)
        self._cached_schedules: dict[int, list] = {}

    async def _async_update_data(self) -> EasytronData:
        try:
            return await self._fetch()
        except EasytronAuthError as err:
            raise UpdateFailed(f"Auth failed: {err}") from err
        except EasytronApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

    async def _fetch(self) -> EasytronData:
        client = self.client

        async def _safe(coro, name):
            try:
                return await coro
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EASYTRON fetch %s failed: %s", name, err)
                return None

        now = datetime.now(tz=timezone.utc)
        refresh_version = (
            self._version_cached is None
            or self._version_last is None
            or (now - self._version_last) > VERSION_REFRESH_INTERVAL
        )

        tasks = {
            "dbmodules": client.dbmodules(),
            "allmodules": client.allmodules(),
            "roomlist": client.room_list(),
            "systemstate": client.systemstate(),
            "ping": client.ping(),
            "datetime": client.datetime_get(),
            "sysinfo": client.systeminformation_get(),
            "daylist": client.daylist(),
        }
        if refresh_version:
            tasks["version"] = client.version()

        results = await asyncio.gather(
            *[_safe(t, k) for k, t in tasks.items()]
        )
        res = dict(zip(tasks.keys(), results))

        db = res.get("dbmodules") or {}
        if not db or not db.get("modules"):
            raise UpdateFailed("dbmodules returned empty — device unreachable")

        allmod = res.get("allmodules")
        if allmod and allmod.get("success") is False:
            # heatapp daemon still warming — reuse last rooms
            _LOGGER.debug("allmodules: %s — reusing cached rooms", allmod.get("message"))
            allmod = self._last_allmodules
        elif allmod and allmod.get("modules"):
            self._last_allmodules = allmod

        if refresh_version and res.get("version"):
            self._version_cached = res["version"]
            self._version_last = now

        data = EasytronData()

        # ---- Devices from dbmodules ----
        db_modules: dict[str, Any] = db.get("modules") or {}
        for did, m in db_modules.items():
            data.devices[did] = DeviceState(
                id=did,
                name=m.get("name") or did,
                room=m.get("room") or "",
                room_id=None,
                node_id=_as_int(m.get("nodeid")),
                type=m.get("type") or "unknown",
                current_temperature=_as_float(m.get("currentTemperature")),
                battery=_as_int(m.get("battery")),
                is_failed=bool(m.get("isFailed")),
                last_response=_as_int(m.get("lastResponse")),
                interview_done=bool(m.get("interviewDone")),
                vendor_id=m.get("vendorId"),
                product_id=m.get("productId"),
                instances=list(m.get("instances") or []),
                raw=m,
            )

        # ---- Rooms from allmodules ----
        if allmod and allmod.get("modules", {}).get("rooms"):
            rooms_raw = allmod["modules"]["rooms"]
            for rid_s, r in rooms_raw.items():
                try:
                    rid = int(rid_s)
                except (TypeError, ValueError):
                    continue
                room_modules = r.get("modules") or {}
                room = RoomState(
                    id=rid,
                    name=r.get("name") or f"Room {rid}",
                    min_temperature=_as_float(r.get("minTemperature")),
                    max_temperature=_as_float(r.get("maxTemperature")),
                    device_ids=list(room_modules.keys()),
                    raw=r,
                )
                data.rooms[rid] = room
                for did in room.device_ids:
                    if did in data.devices:
                        data.devices[did].room_id = rid
                        if not data.devices[did].room:
                            data.devices[did].room = room.name
            self._last_rooms = data.rooms
        else:
            data.rooms = self._last_rooms

        # ---- Merge room_list data (desired/actual temps, comfort mode) ----
        # room_list returns groups[].rooms[] (list of dicts with "id" field)
        roomlist = res.get("roomlist") or {}
        for group in roomlist.get("groups") or []:
            for rl in group.get("rooms") or []:
                rid = _as_int(rl.get("id"))
                if rid is None:
                    continue
                # Create room if not already in allmodules
                if rid not in data.rooms:
                    data.rooms[rid] = RoomState(
                        id=rid,
                        name=rl.get("name") or f"Room {rid}",
                        min_temperature=_as_float(rl.get("minTemperature")),
                        max_temperature=_as_float(rl.get("maxTemperature")),
                    )
                room = data.rooms[rid]
                room.desired_temperature = _as_float(rl.get("desiredTemperature"))
                room.desired_temp_day = _as_float(rl.get("desiredTempDay"))
                room.desired_temp_night = _as_float(rl.get("desiredTempNight"))
                room.actual_temperature = _as_float(rl.get("actualTemperature"))
                room.is_comfort_mode = rl.get("isComfortMode")
                room.window_open = bool(rl.get("windowPosition"))
                room.cooling = bool(rl.get("cooling"))
                if room.min_temperature is None:
                    room.min_temperature = _as_float(rl.get("minTemperature"))
                if room.max_temperature is None:
                    room.max_temperature = _as_float(rl.get("maxTemperature"))

        # ---- Schedules (every 5 min) ----
        refresh_schedules = (
            self._schedule_last is None
            or (now - self._schedule_last) > self._schedule_interval
        )
        if refresh_schedules and data.rooms:
            sched_tasks = {
                rid: _safe(client.get_switchingtimes(rid), f"schedule_{rid}")
                for rid in data.rooms
            }
            sched_results = await asyncio.gather(*sched_tasks.values())
            for rid, result in zip(sched_tasks.keys(), sched_results):
                if result and isinstance(result, dict) and result.get("switchingtimes"):
                    self._cached_schedules[rid] = result["switchingtimes"]
            self._schedule_last = now
        for rid, room in data.rooms.items():
            room.schedule = self._cached_schedules.get(rid, [])

        # ---- System state ----
        sys = SystemState()
        sys.controller_state = db.get("controllerState")
        reorg = db.get("reorganization") or {}
        sys.reorganization_running = bool(reorg.get("running"))
        sys.reorganization_start_time = _as_int(reorg.get("startTime"))
        sys.reorganization_duration = _as_int(reorg.get("duration"))
        sys.current_time = _as_int(db.get("currentTime"))
        sys.on_maintenance = bool(db.get("onMaintenance"))

        ping = res.get("ping") or {}
        sys.uniqueid = ping.get("uniqueid")
        sys.remote_address = ping.get("remoteAddress")

        if self._version_cached:
            v = self._version_cached
            sys.server_version = v.get("server")
            sys.firmware = v.get("server") or v.get("heatcom")
            sys.home_id = v.get("zway_homeid")

        sysinfo = res.get("sysinfo") or {}
        sys.name = sysinfo.get("name")
        sys.location = sysinfo.get("location")

        dt = res.get("datetime") or {}
        sys.internet = dt.get("internet")

        sstate = res.get("systemstate") or {}
        sys.errors = sstate.get("errors") or []

        dayl = res.get("daylist") or {}
        sys.daylist = dayl.get("dayList") or []

        data.system = sys

        # ---- Z-Way mesh (best-effort, read-only, every 5 min) ----
        refresh_zway = (
            self._zway_last is None
            or (now - self._zway_last) > self._zway_interval
        )
        if refresh_zway:
            node_ids = [d.node_id for d in data.devices.values() if d.node_id]
            if node_ids:
                neighbour_tasks = [client.zway_neighbours(nid) for nid in node_ids]
                last_rx_tasks = [client.zway_last_received(nid) for nid in node_ids]
                try:
                    neighbour_results = await asyncio.gather(
                        *neighbour_tasks, return_exceptions=True
                    )
                    last_rx_results = await asyncio.gather(
                        *last_rx_tasks, return_exceptions=True
                    )
                    for nid, n, lr in zip(
                        node_ids, neighbour_results, last_rx_results
                    ):
                        if isinstance(n, list):
                            data.mesh[nid] = n
                        if isinstance(lr, (int, float)):
                            data.zway_last_received[nid] = float(lr)
                    self._zway_last = now
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Z-Way mesh fetch failed: %s", err)
        else:
            # Reuse cached mesh data
            if self.data:
                data.mesh = self.data.mesh
                data.zway_last_received = self.data.zway_last_received

        return data


def _as_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
