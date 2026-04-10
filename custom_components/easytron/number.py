"""Number platform — per-room temperature settings."""
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
        entities.append(EasytronRoomDayTempNumber(coord, rid))
        entities.append(EasytronRoomNightTempNumber(coord, rid))
        entities.append(EasytronRoomMinTempNumber(coord, rid))
        entities.append(EasytronRoomMaxTempNumber(coord, rid))
    async_add_entities(entities)


class _RoomTempBase(EasytronRoomEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 5
    _attr_native_max_value = 30
    _attr_native_step = 0.5
    _attr_mode = NumberMode.SLIDER


class EasytronRoomDayTempNumber(_RoomTempBase):
    def __init__(self, coord, rid: int) -> None:
        super().__init__(coord, rid)
        self._attr_unique_id = f"easytron_{self._host}_room_{rid}_day_temperature"
        self._attr_name = "Day temperature"

    @property
    def native_value(self) -> float | None:
        room = self.room
        return room.desired_temp_day if room else None

    @property
    def native_min_value(self) -> float:
        room = self.room
        if room and room.min_temperature is not None:
            return float(room.min_temperature)
        return 5.0

    @property
    def native_max_value(self) -> float:
        room = self.room
        if room and room.max_temperature is not None:
            return float(room.max_temperature)
        return 30.0

    async def async_set_native_value(self, value: float) -> None:
        # Set day temp by temporarily switching to comfort mode
        result = await self.coordinator.client.set_temperature(
            self._room_id, float(value)
        )
        if not result.get("success"):
            _LOGGER.error("Room %s day temp=%s failed: %s", self._room_id, value, result)
        await self.coordinator.async_request_refresh()


class EasytronRoomNightTempNumber(_RoomTempBase):
    def __init__(self, coord, rid: int) -> None:
        super().__init__(coord, rid)
        self._attr_unique_id = f"easytron_{self._host}_room_{rid}_night_temperature"
        self._attr_name = "Night temperature"

    @property
    def native_value(self) -> float | None:
        room = self.room
        return room.desired_temp_night if room else None

    @property
    def native_min_value(self) -> float:
        room = self.room
        if room and room.min_temperature is not None:
            return float(room.min_temperature)
        return 5.0

    @property
    def native_max_value(self) -> float:
        room = self.room
        if room and room.max_temperature is not None:
            return float(room.max_temperature)
        return 30.0

    async def async_set_native_value(self, value: float) -> None:
        result = await self.coordinator.client.set_temperature(
            self._room_id, float(value)
        )
        if not result.get("success"):
            _LOGGER.error("Room %s night temp=%s failed: %s", self._room_id, value, result)
        await self.coordinator.async_request_refresh()


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
            "Room %s min_temperature=%s — read-only bound",
            self._room_id, value,
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
            "Room %s max_temperature=%s — read-only bound",
            self._room_id, value,
        )
