"""Sensor platform for EASYTRON."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OFFLINE_THRESHOLD_SECONDS
from .coordinator import EasytronCoordinator
from .entity import EasytronDeviceEntity, EasytronSystemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: EasytronCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list = []

    # Per-device sensors
    for did, dev in coord.data.devices.items():
        entities.append(EasytronTemperatureSensor(coord, did))
        entities.append(EasytronBatterySensor(coord, did))
        entities.append(EasytronLastSeenSensor(coord, did))
        entities.append(EasytronNodeIdSensor(coord, did))
        entities.append(EasytronZwaveSignalSensor(coord, did))

    # System sensors
    entities.extend(
        [
            EasytronControllerStateSensor(coord),
            EasytronHomeIdSensor(coord),
            EasytronFirmwareSensor(coord),
            EasytronTotalDevicesSensor(coord),
            EasytronFailedDevicesSensor(coord),
            EasytronOfflineDevicesSensor(coord),
            EasytronAverageBatterySensor(coord),
            EasytronMinBatterySensor(coord),
            EasytronMeshSizeSensor(coord),
            EasytronMeshBuiltSensor(coord),
            EasytronReorgRunningSensor(coord),
            EasytronReorgLastRunSensor(coord),
            EasytronRemoteIpSensor(coord),
            EasytronSystemErrorsSensor(coord),
        ]
    )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Per-device
# ---------------------------------------------------------------------------


class EasytronTemperatureSensor(EasytronDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_translation_key = "temperature"

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_temperature"
        self._attr_name = "Temperature"

    @property
    def native_value(self) -> float | None:
        d = self.device
        return d.current_temperature if d else None

    @property
    def available(self) -> bool:
        d = self.device
        return super().available and d is not None and d.current_temperature is not None


class EasytronBatterySensor(EasytronDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_battery"
        self._attr_name = "Battery"

    @property
    def native_value(self) -> int | None:
        d = self.device
        return d.battery if d else None

    @property
    def available(self) -> bool:
        d = self.device
        return super().available and d is not None and d.battery is not None


class EasytronLastSeenSensor(EasytronDeviceEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_last_seen"
        self._attr_name = "Last seen"

    @property
    def native_value(self) -> datetime | None:
        d = self.device
        if not d or d.last_response is None:
            return None
        try:
            return datetime.fromtimestamp(d.last_response, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None


class EasytronNodeIdSensor(EasytronDeviceEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_nodeid"
        self._attr_name = "Z-Wave node ID"

    @property
    def native_value(self) -> int | None:
        d = self.device
        return d.node_id if d else None


class EasytronZwaveSignalSensor(EasytronDeviceEntity, SensorEntity):
    """Proxy 'signal' quality from freshness of Z-Way lastReceived timestamp."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"

    def __init__(self, coord, did: str) -> None:
        super().__init__(coord, did)
        self._attr_unique_id = f"easytron_{self._host}_{did}_signal_age"
        self._attr_name = "Last radio frame age"

    @property
    def native_value(self) -> int | None:
        d = self.device
        if not d or d.node_id is None:
            return None
        lr = self.coordinator.data.zway_last_received.get(d.node_id)
        if lr is None:
            return None
        return max(0, int(datetime.now(tz=timezone.utc).timestamp() - lr))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.device
        if not d or d.node_id is None:
            return None
        neighbours = self.coordinator.data.mesh.get(d.node_id) or []
        return {
            "neighbours": neighbours,
            "neighbour_count": len(neighbours),
        }


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class _SysBase(EasytronSystemEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC


class EasytronControllerStateSensor(_SysBase):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_controller_state"
        self._attr_name = "Controller state"

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.system.controller_state


class EasytronHomeIdSensor(_SysBase):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_homeid"
        self._attr_name = "Z-Wave home ID"

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.system.home_id


class EasytronFirmwareSensor(_SysBase):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_firmware"
        self._attr_name = "Firmware"

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.system.firmware


class EasytronTotalDevicesSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_total_devices"
        self._attr_name = "Total devices"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.devices)


class EasytronFailedDevicesSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_failed_devices"
        self._attr_name = "Failed devices"

    @property
    def native_value(self) -> int:
        return sum(1 for d in self.coordinator.data.devices.values() if d.is_failed)


class EasytronOfflineDevicesSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_offline_devices"
        self._attr_name = "Offline devices"

    @property
    def native_value(self) -> int:
        now = datetime.now(tz=timezone.utc).timestamp()
        count = 0
        for d in self.coordinator.data.devices.values():
            if d.is_failed:
                count += 1
                continue
            if d.last_response and (now - d.last_response) > OFFLINE_THRESHOLD_SECONDS:
                count += 1
        return count


class EasytronAverageBatterySensor(_SysBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_average_battery"
        self._attr_name = "Average battery"

    @property
    def native_value(self) -> float | None:
        vals = [
            d.battery
            for d in self.coordinator.data.devices.values()
            if d.battery is not None and d.battery > 0
        ]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 1)


class EasytronMinBatterySensor(_SysBase):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_min_battery"
        self._attr_name = "Minimum battery"

    @property
    def native_value(self) -> int | None:
        vals = [
            d.battery
            for d in self.coordinator.data.devices.values()
            if d.battery is not None and d.battery > 0
        ]
        return min(vals) if vals else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        worst = None
        for d in self.coordinator.data.devices.values():
            if d.battery is None or d.battery <= 0:
                continue
            if worst is None or d.battery < worst.battery:
                worst = d
        if not worst:
            return {}
        return {"worst_device": worst.name, "worst_device_id": worst.id}


class EasytronMeshSizeSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_mesh_size"
        self._attr_name = "Mesh size"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.mesh) or len(
            [d for d in self.coordinator.data.devices.values() if d.node_id]
        )


class EasytronMeshBuiltSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_mesh_built"
        self._attr_name = "Nodes with mesh neighbours"

    @property
    def native_value(self) -> int:
        return sum(1 for n in self.coordinator.data.mesh.values() if n)


class EasytronReorgRunningSensor(_SysBase):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_reorg_running"
        self._attr_name = "Network heal running"

    @property
    def native_value(self) -> str:
        return "on" if self.coordinator.data.system.reorganization_running else "off"


class EasytronReorgLastRunSensor(_SysBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_reorg_last_run"
        self._attr_name = "Network heal last start"

    @property
    def native_value(self) -> datetime | None:
        ts = self.coordinator.data.system.reorganization_start_time
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None


class EasytronRemoteIpSensor(_SysBase):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_remote_ip"
        self._attr_name = "Remote address (ISG)"

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.system.remote_address


class EasytronSystemErrorsSensor(_SysBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_system_errors"
        self._attr_name = "System errors"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.system.errors)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"errors": self.coordinator.data.system.errors}
