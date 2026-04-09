"""Number platform — per-room min/max temperature bounds.

These are exposed as read-only informational values for now (no server-side
room-edit endpoint has been reverse-engineered). Setting raises a warning.
"""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EasytronCoordinator
from .entity import EasytronRoomEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: EasytronCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list = []
    for rid in coord.data.rooms:
        entities.append(EasytronRoomMinTempNumber(coord, rid))
        entities.append(EasytronRoomMaxTempNumber(coord, rid))
    async_add_entities(entities)


class _RoomBoundBase(EasytronRoomEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 5
    _attr_native_max_value = 30
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG


class EasytronRoomMinTempNumber(_RoomBoundBase):
    def __init__(self, coord, rid: int) -> None:
        super().__init__(coord, rid)
        self._attr_unique_id = f"easytron_{self._host}_room_{rid}_min_temperature"
        self._attr_name = "Min temperature"

    @property
    def native_value(self) -> float | None:
        room = self.room
        return room.min_temperature if room else None

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.warning(
            "Room %s min_temperature=%s — room-bound write endpoint not "
            "reverse-engineered, change not persisted",
            self._room_id,
            value,
        )


class EasytronRoomMaxTempNumber(_RoomBoundBase):
    def __init__(self, coord, rid: int) -> None:
        super().__init__(coord, rid)
        self._attr_unique_id = f"easytron_{self._host}_room_{rid}_max_temperature"
        self._attr_name = "Max temperature"

    @property
    def native_value(self) -> float | None:
        room = self.room
        return room.max_temperature if room else None

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.warning(
            "Room %s max_temperature=%s — room-bound write endpoint not "
            "reverse-engineered, change not persisted",
            self._room_id,
            value,
        )
