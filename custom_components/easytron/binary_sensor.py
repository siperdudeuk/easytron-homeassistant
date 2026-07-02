"""Binary sensor platform for EASYTRON."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    OFFLINE_THRESHOLD_SECONDS,
    ROOMSTATUS_ACTIVE_CODES,
    ROOMSTATUS_STANDBY_CODES,
    TYPE_THERMOSTAT,
)
from .coordinator import EasytronCoordinator
from .entity import EasytronDeviceEntity, EasytronRoomEntity, EasytronSystemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: EasytronCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list = []

    for did in coord.data.devices:
        entities.append(EasytronDeviceOnlineBinarySensor(coord, did))
        entities.append(EasytronDeviceFailedBinarySensor(coord, did))
        entities.append(EasytronDeviceInterviewBinarySensor(coord, did))

    for rid in coord.data.rooms:
        entities.append(EasytronRoomStandbyBinarySensor(coord, rid))

    entities.extend(
        [
            EasytronHeatingActiveBinarySensor(coord),
            EasytronMaintenanceBinarySensor(coord),
            EasytronInternetBinarySensor(coord),
            EasytronAllRoomsStandbyBinarySensor(coord),
        ]
    )
    async_add_entities(entities)


class EasytronDeviceOnlineBinarySensor(EasytronDeviceEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_online"
        self._attr_name = "Online"

    @property
    def is_on(self) -> bool:
        d = self.device
        if not d:
            return False
        if d.is_failed:
            return False
        if d.last_response is None:
            return True
        age = datetime.now(tz=timezone.utc).timestamp() - d.last_response
        return age < OFFLINE_THRESHOLD_SECONDS


class EasytronDeviceFailedBinarySensor(EasytronDeviceEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_failed"
        self._attr_name = "Failed"

    @property
    def is_on(self) -> bool:
        d = self.device
        return bool(d and d.is_failed)


class EasytronDeviceInterviewBinarySensor(EasytronDeviceEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_interview_complete"
        self._attr_name = "Interview complete"

    @property
    def is_on(self) -> bool:
        d = self.device
        return bool(d and d.interview_done)


class EasytronHeatingActiveBinarySensor(EasytronSystemEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_heating_active"
        self._attr_name = "Heating active"

    @property
    def is_on(self) -> bool:
        # Any thermostat reporting a call-for-heat flag in its instances.
        for d in self.coordinator.data.devices.values():
            if d.type != TYPE_THERMOSTAT:
                continue
            for inst in d.instances:
                if (
                    inst.get("heatingActive")
                    or inst.get("calling")
                    or inst.get("callForHeat")
                ):
                    return True
            if d.raw.get("callForHeat") or d.raw.get("heatingActive"):
                return True
        return False


class EasytronMaintenanceBinarySensor(EasytronSystemEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_maintenance"
        self._attr_name = "In service mode"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.system.on_maintenance)


class EasytronRoomStandbyBinarySensor(EasytronRoomEntity, BinarySensorEntity):
    """On when the room is in heatapp standby (target pinned to min)."""

    def __init__(self, coord, room_id: int) -> None:
        super().__init__(coord, room_id)
        self._attr_unique_id = f"easytron_{self._host}_room_{room_id}_standby"
        self._attr_name = "Standby"

    @property
    def is_on(self) -> bool | None:
        r = self.room
        if not r or r.roomstatus is None:
            return None
        if r.roomstatus in ROOMSTATUS_STANDBY_CODES:
            return True
        if r.roomstatus in ROOMSTATUS_ACTIVE_CODES:
            return False
        return None

    @property
    def extra_state_attributes(self) -> dict:
        r = self.room
        return {"roomstatus": r.roomstatus if r else None}


class EasytronAllRoomsStandbyBinarySensor(EasytronSystemEntity, BinarySensorEntity):
    """On when every room is in standby (ISG mode-change trigger)."""

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_all_rooms_standby"
        self._attr_name = "All rooms standby"

    @property
    def is_on(self) -> bool | None:
        rooms = list((self.coordinator.data.rooms or {}).values())
        considered = [r for r in rooms if r.roomstatus is not None]
        if not considered:
            return None
        return all(r.roomstatus in ROOMSTATUS_STANDBY_CODES for r in considered)

    @property
    def extra_state_attributes(self) -> dict:
        rooms = list((self.coordinator.data.rooms or {}).values())
        standby = [r.name for r in rooms if r.roomstatus in ROOMSTATUS_STANDBY_CODES]
        active = [r.name for r in rooms if r.roomstatus in ROOMSTATUS_ACTIVE_CODES]
        unknown = [
            r.name for r in rooms
            if r.roomstatus is not None
            and r.roomstatus not in ROOMSTATUS_STANDBY_CODES
            and r.roomstatus not in ROOMSTATUS_ACTIVE_CODES
        ]
        return {
            "standby_rooms": standby,
            "active_rooms": active,
            "unknown_rooms": unknown,
        }


class EasytronInternetBinarySensor(EasytronSystemEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_internet"
        self._attr_name = "Internet"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.system.internet)
