"""Button platform for EASYTRON."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EasytronCoordinator
from .entity import EasytronSystemEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord: EasytronCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            EasytronReorganizeButton(coord),
            EasytronRebootButton(coord),
            EasytronRefreshButton(coord),
            EasytronStartInclusionButton(coord),
            EasytronStartExclusionButton(coord),
            EasytronStopLearnModeButton(coord),
        ]
    )


class _Base(EasytronSystemEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG


class EasytronReorganizeButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_reorganize"
        self._attr_name = "Reorganize Z-Wave network"

    async def async_press(self) -> None:
        await self.coordinator.client.reorganize()
        await self.coordinator.async_request_refresh()


class EasytronRebootButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_reboot"
        self._attr_name = "Reboot base station"

    async def async_press(self) -> None:
        _LOGGER.warning("EASYTRON reboot pressed — device will be unreachable for ~3 minutes")
        await self.coordinator.client.reboot()


class EasytronRefreshButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_refresh"
        self._attr_name = "Refresh data"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class EasytronStartInclusionButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_start_inclusion"
        self._attr_name = "Start Z-Wave inclusion (28s)"

    async def async_press(self) -> None:
        await self.coordinator.client.start_inclusion()


class EasytronStartExclusionButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_start_exclusion"
        self._attr_name = "Start Z-Wave exclusion (28s)"

    async def async_press(self) -> None:
        await self.coordinator.client.start_exclusion()


class EasytronStopLearnModeButton(_Base):
    def __init__(self, coord) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"easytron_{self._host}_stop_learnmode"
        self._attr_name = "Stop learn mode"

    async def async_press(self) -> None:
        await self.coordinator.client.stop_learnmode()
