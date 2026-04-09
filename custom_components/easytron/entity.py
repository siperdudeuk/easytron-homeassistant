"""Common entity base for EASYTRON."""
from __future__ import annotations

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import DeviceState, EasytronCoordinator


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "unknown"


class EasytronBaseEntity(CoordinatorEntity[EasytronCoordinator]):
    """Base for all EASYTRON entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EasytronCoordinator) -> None:
        super().__init__(coordinator)
        self._host = coordinator.client.host

    @property
    def _system_device_info(self) -> DeviceInfo:
        sys = self.coordinator.data.system if self.coordinator.data else None
        return DeviceInfo(
            identifiers={(DOMAIN, f"system_{self._host}")},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=sys.name if sys and sys.name else f"EASYTRON {self._host}",
            sw_version=sys.server_version if sys else None,
            configuration_url=f"http://{self._host}",
        )


class EasytronDeviceEntity(EasytronBaseEntity):
    """Base for per-Z-Wave-device entities."""

    def __init__(
        self,
        coordinator: EasytronCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def device(self) -> DeviceState | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.devices.get(self._device_id)

    @property
    def available(self) -> bool:
        return super().available and self.device is not None

    @property
    def device_info(self) -> DeviceInfo:
        d = self.device
        name = d.name if d else self._device_id
        node = d.node_id if d else None
        model = d.type if d else None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}_{self._device_id}")},
            manufacturer=MANUFACTURER,
            model=model or "Z-Wave device",
            name=name,
            via_device=(DOMAIN, f"system_{self._host}"),
            sw_version=str(node) if node else None,
        )


class EasytronSystemEntity(EasytronBaseEntity):
    """Base for system-level (hub) entities."""

    @property
    def device_info(self) -> DeviceInfo:
        return self._system_device_info


class EasytronRoomEntity(EasytronBaseEntity):
    """Base for per-room entities (climate, number)."""

    def __init__(
        self,
        coordinator: EasytronCoordinator,
        room_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._room_id = room_id

    @property
    def room(self):
        data = self.coordinator.data
        if not data:
            return None
        return data.rooms.get(self._room_id)

    @property
    def available(self) -> bool:
        return super().available and self.room is not None

    @property
    def device_info(self) -> DeviceInfo:
        r = self.room
        name = r.name if r else f"Room {self._room_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}_room_{self._room_id}")},
            manufacturer=MANUFACTURER,
            model="Room",
            name=f"Room: {name}",
            via_device=(DOMAIN, f"system_{self._host}"),
        )
