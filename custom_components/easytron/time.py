"""Time platform for EASYTRON — day/night schedule per room."""
from __future__ import annotations

import logging
from datetime import time as dt_time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EasytronCoordinator
from .entity import EasytronRoomEntity

_LOGGER = logging.getLogger(__name__)

# Switching times format: 21 pipe-separated entries (7 days × 3 slots)
# Each entry is "from-to" (hours as floats) or empty
# Night mode (L) entries define when night temp applies;
# gaps between them use day temp.
#
# Common pattern: night from 0-WAKE and SLEEP-24 each day
# e.g. "0-5.5|22.5-24||0-5.5|22.5-24||..." (3 slots per day, 3rd usually empty)


def _hours_to_time(h: float) -> dt_time:
    """Convert float hours (e.g. 5.5) to datetime.time (05:30)."""
    hours = int(h)
    minutes = int((h - hours) * 60)
    return dt_time(hour=min(hours, 23), minute=minutes)


def _time_to_hours(t: dt_time) -> float:
    """Convert datetime.time to float hours."""
    return t.hour + t.minute / 60.0


def _build_schedule(day_start: float, night_start: float) -> str:
    """Build a 21-entry pipe-separated schedule string.

    Night mode runs from 0:00 to day_start and from night_start to 24:00.
    This is applied uniformly to all 7 days.

    Special cases:
    - day_start=0 and night_start=0: always day (no night periods)
    - day_start=0 and night_start>=24: always night
    """
    if day_start <= 0 and night_start <= 0:
        # Always day — no night periods at all
        return "||||||||||||||||||||"
    if day_start <= 0:
        # No morning night period, just evening
        day_entry = f"{night_start}-24||"
    elif night_start >= 24:
        # No evening night period, just morning
        day_entry = f"0-{day_start}||"
    else:
        day_entry = f"0-{day_start}|{night_start}-24|"
    return "|".join([day_entry] * 7)


def _parse_schedule(switchingtimes: list[Any]) -> tuple[float | None, float | None]:
    """Extract day_start and night_start from the first day's schedule.

    Returns (day_start_hours, night_start_hours) or None if not parseable.
    """
    if not switchingtimes or len(switchingtimes) < 3:
        return None, None

    # First day's 3 slots are entries 0, 1, 2
    day_start = None
    night_start = None

    for entry in switchingtimes[:3]:
        if entry is None:
            continue
        fr = entry.get("from")
        to = entry.get("to")
        if fr is None or to is None:
            continue
        fr = float(fr)
        to = float(to)
        # Night period starting at 0 = morning, the "to" is when day starts
        if fr == 0 or fr < 1:
            day_start = to
        # Night period ending at 24 = evening, the "from" is when night starts
        if to >= 23.5:
            night_start = fr

    return day_start, night_start


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: EasytronCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list = []
    for rid in coord.data.rooms:
        entities.append(EasytronDayStartTime(coord, rid))
        entities.append(EasytronNightStartTime(coord, rid))
    async_add_entities(entities)


class EasytronDayStartTime(EasytronRoomEntity, TimeEntity):
    """Time when day/comfort mode starts (morning wake-up time)."""

    def __init__(self, coord: EasytronCoordinator, room_id: int) -> None:
        super().__init__(coord, room_id)
        self._attr_unique_id = f"easytron_{self._host}_room_{room_id}_day_start"
        self._attr_name = "Day mode starts"
        self._cached_day_start: float | None = None
        self._cached_night_start: float | None = None

    @property
    def native_value(self) -> dt_time | None:
        room = self.room
        if not room:
            return None
        if not room.schedule:
            # No schedule = always day, show 00:00 (day starts at midnight)
            return dt_time(0, 0)
        day_start, _ = _parse_schedule(room.schedule)
        if day_start is None:
            # No night periods found = always day
            return dt_time(0, 0)
        return _hours_to_time(day_start)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        room = self.room
        if not room:
            return {}
        day_start, night_start = _parse_schedule(room.schedule) if room.schedule else (None, None)
        always_day = day_start is None and night_start is None
        return {"always_day_mode": always_day}

    async def async_set_value(self, value: dt_time) -> None:
        room = self.room
        if not room:
            return
        new_day_start = _time_to_hours(value)
        # Get current night_start from schedule
        _, night_start = _parse_schedule(room.schedule) if room.schedule else (None, None)
        if night_start is None:
            night_start = 0.0 if new_day_start == 0 else 22.0

        schedule_str = _build_schedule(new_day_start, night_start)
        result = await self.coordinator.client.set_switchingtimes(
            self._room_id, schedule_str
        )
        if not result.get("success"):
            _LOGGER.error("Room %s set day start failed: %s", self._room_id, result)
            return
        # Refresh schedule data
        await self._refresh_schedule()

    async def _refresh_schedule(self) -> None:
        """Fetch updated schedule and refresh coordinator."""
        try:
            st = await self.coordinator.client.get_switchingtimes(self._room_id)
            room = self.room
            if room and st.get("switchingtimes"):
                room.schedule = st["switchingtimes"]
        except Exception:  # noqa: BLE001
            pass
        await self.coordinator.async_request_refresh()


class EasytronNightStartTime(EasytronRoomEntity, TimeEntity):
    """Time when night/setback mode starts (evening bedtime)."""

    def __init__(self, coord: EasytronCoordinator, room_id: int) -> None:
        super().__init__(coord, room_id)
        self._attr_unique_id = f"easytron_{self._host}_room_{room_id}_night_start"
        self._attr_name = "Night mode starts"

    @property
    def native_value(self) -> dt_time | None:
        room = self.room
        if not room:
            return None
        if not room.schedule:
            return dt_time(0, 0)
        _, night_start = _parse_schedule(room.schedule)
        if night_start is None:
            return dt_time(0, 0)
        return _hours_to_time(night_start)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        room = self.room
        if not room:
            return {}
        day_start, night_start = _parse_schedule(room.schedule) if room.schedule else (None, None)
        always_day = day_start is None and night_start is None
        return {"always_day_mode": always_day}

    async def async_set_value(self, value: dt_time) -> None:
        room = self.room
        if not room:
            return
        new_night_start = _time_to_hours(value)
        # Get current day_start from schedule
        day_start, _ = _parse_schedule(room.schedule) if room.schedule else (None, None)
        if day_start is None:
            day_start = 0.0 if new_night_start == 0 else 6.0

        schedule_str = _build_schedule(day_start, new_night_start)
        result = await self.coordinator.client.set_switchingtimes(
            self._room_id, schedule_str
        )
        if not result.get("success"):
            _LOGGER.error("Room %s set night start failed: %s", self._room_id, result)
            return
        # Refresh schedule data
        try:
            st = await self.coordinator.client.get_switchingtimes(self._room_id)
            room_obj = self.room
            if room_obj and st.get("switchingtimes"):
                room_obj.schedule = st["switchingtimes"]
        except Exception:  # noqa: BLE001
            pass
        await self.coordinator.async_request_refresh()
