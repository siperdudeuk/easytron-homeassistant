"""Switch platform — placeholder per-room active switches.

A reliable per-room enable/disable endpoint hasn't been reverse-engineered,
so these switches are informational and log-only. Kept for UI completeness
and to provide an obvious toggle point once the API is known.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_FLOOR, TYPE_THERMOSTAT
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
    data = coord.data
    for rid, room in data.rooms.items():
        has_heating = any(
            data.devices.get(did) and data.devices[did].type in (TYPE_THERMOSTAT, TYPE_FLOOR)
            for did in room.device_ids
        )
        if has_heating:
            entities.append(EasytronRoomActiveSwitch(coord, rid))
    async_add_entities(entities)


class EasytronRoomActiveSwitch(EasytronRoomEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coord, rid: int) -> None:
        super().__init__(coord, rid)
        self._attr_unique_id = f"easytron_{self._host}_room_{rid}_active"
        self._attr_name = "Heating active"
        self._state = True  # optimistic

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.warning(
            "Room %s: turn_on requested — room-active endpoint not "
            "reverse-engineered",
            self._room_id,
        )
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.warning(
            "Room %s: turn_off requested — room-active endpoint not "
            "reverse-engineered",
            self._room_id,
        )
        self._state = False
        self.async_write_ha_state()
