"""Diagnostics support for EASYTRON."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .coordinator import EasytronCoordinator

TO_REDACT_ENTRY = {CONF_USERNAME, CONF_PASSWORD}
TO_REDACT_TOP = {"remoteAddress", "mac", "servicecode", "sysinfo_macaddress"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    bucket = hass.data[DOMAIN][entry.entry_id]
    coord: EasytronCoordinator = bucket["coordinator"]
    client = bucket["client"]

    async def _safe(coro):
        try:
            return await coro
        except Exception as err:  # noqa: BLE001
            return {"_error": str(err)}

    dbmodules = await _safe(client.dbmodules())
    allmodules = await _safe(client.allmodules())
    version = await _safe(client.version())
    daylist = await _safe(client.daylist())
    systemstate = await _safe(client.systemstate())

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
        "dbmodules": async_redact_data(dbmodules, TO_REDACT_TOP),
        "allmodules": async_redact_data(allmodules, TO_REDACT_TOP),
        "version": async_redact_data(version, TO_REDACT_TOP),
        "daylist": daylist,
        "systemstate": systemstate,
        "coordinator": {
            "device_count": len(coord.data.devices) if coord.data else 0,
            "room_count": len(coord.data.rooms) if coord.data else 0,
            "mesh_nodes": len(coord.data.mesh) if coord.data else 0,
        },
    }
