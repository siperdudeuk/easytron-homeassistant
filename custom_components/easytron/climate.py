"""Climate platform for EASYTRON — one entity per heating room."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TYPE_FLOOR, TYPE_SENSOR, TYPE_THERMOSTAT
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
        # Only rooms that contain a thermostat or floor port
        has_heating = any(
            data.devices.get(did) and data.devices[did].type in (TYPE_THERMOSTAT, TYPE_FLOOR)
            for did in room.device_ids
        )
        if has_heating:
            entities.append(EasytronRoomClimate(coord, rid))
    async_add_entities(entities)


class EasytronRoomClimate(EasytronRoomEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _attr_name = None  # use room device name

    def __init__(self, coord: EasytronCoordinator, room_id: int) -> None:
        super().__init__(coord, room_id)
        self._attr_unique_id = f"easytron_{self._host}_room_{room_id}"

    # ------------------------------------------------------------------
    @property
    def current_temperature(self) -> float | None:
        room = self.room
        if not room:
            return None
        # Prefer room_list actual temperature (authoritative)
        if room.actual_temperature is not None:
            return room.actual_temperature
        devices = self.coordinator.data.devices
        # Fallback: prefer an actual room sensor
        for did in room.device_ids:
            d = devices.get(did)
            if d and d.type == TYPE_SENSOR and d.current_temperature is not None:
                return d.current_temperature
        # Otherwise average the thermostats
        vals = [
            devices[did].current_temperature
            for did in room.device_ids
            if did in devices
            and devices[did].type == TYPE_THERMOSTAT
            and devices[did].current_temperature is not None
        ]
        if vals:
            return round(sum(vals) / len(vals), 1)
        return None

    @property
    def target_temperature(self) -> float | None:
        room = self.room
        if not room:
            return None
        if room.desired_temperature is not None:
            return room.desired_temperature
        return None

    @property
    def min_temp(self) -> float:
        room = self.room
        if room and room.min_temperature is not None:
            return float(room.min_temperature)
        return 5.0

    @property
    def max_temp(self) -> float:
        room = self.room
        if room and room.max_temperature is not None:
            return float(room.max_temperature)
        return 30.0

    @property
    def hvac_mode(self) -> HVACMode:
        # Without a reliable per-room off flag, assume HEAT.
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        room = self.room
        if not room:
            return HVACAction.IDLE
        devices = self.coordinator.data.devices
        for did in room.device_ids:
            d = devices.get(did)
            if not d or d.type != TYPE_THERMOSTAT:
                continue
            for inst in d.instances:
                if (
                    inst.get("heatingActive")
                    or inst.get("calling")
                    or inst.get("callForHeat")
                ):
                    return HVACAction.HEATING
            if d.raw.get("heatingActive") or d.raw.get("callForHeat"):
                return HVACAction.HEATING
        return HVACAction.IDLE

    # ------------------------------------------------------------------
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature for this room."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        result = await self.coordinator.client.set_temperature(
            self._room_id, float(temp)
        )
        if not result.get("success"):
            _LOGGER.error(
                "Room %s: set_temperature(%s) failed: %s",
                self._room_id, temp, result,
            )
            return
        _LOGGER.debug(
            "Room %s: set_temperature(%s) success", self._room_id, temp
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        _LOGGER.warning(
            "Room %s: async_set_hvac_mode(%s) — not implemented",
            self._room_id,
            hvac_mode,
        )
