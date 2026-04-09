"""EASYTRON Stiebel Eltron heatapp integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EasytronClient
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
    SERVICE_NETWORK_HEAL,
    SERVICE_REMOVE_DEVICE,
    SERVICE_SET_ROOM_TARGET_TEMPERATURE,
    SERVICE_START_EXCLUSION,
    SERVICE_START_INCLUSION,
)
from .coordinator import EasytronCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORM_LIST = [Platform(p) for p in PLATFORMS]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EASYTRON from a config entry."""
    session = async_get_clientsession(hass)
    client = EasytronClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )
    # Do first login eagerly so any credential issue surfaces early.
    await client.login()

    coordinator = EasytronCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_LIST)

    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORM_LIST
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for svc in (
                SERVICE_NETWORK_HEAL,
                SERVICE_REMOVE_DEVICE,
                SERVICE_SET_ROOM_TARGET_TEMPERATURE,
                SERVICE_START_EXCLUSION,
                SERVICE_START_INCLUSION,
            ):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _get_any_client(hass: HomeAssistant) -> EasytronClient | None:
    data = hass.data.get(DOMAIN) or {}
    for bucket in data.values():
        return bucket["client"]
    return None


def _register_services(hass: HomeAssistant) -> None:
    """Register domain-level services (idempotent)."""

    if hass.services.has_service(DOMAIN, SERVICE_NETWORK_HEAL):
        return

    async def _heal(_call: ServiceCall) -> None:
        client = _get_any_client(hass)
        if client:
            await client.reorganize()

    async def _inc(_call: ServiceCall) -> None:
        client = _get_any_client(hass)
        if client:
            await client.start_inclusion()

    async def _exc(_call: ServiceCall) -> None:
        client = _get_any_client(hass)
        if client:
            await client.start_exclusion()

    async def _rm(call: ServiceCall) -> None:
        client = _get_any_client(hass)
        if client:
            await client.remove_device(call.data["device_id"])

    async def _set_target(call: ServiceCall) -> None:
        # TODO: target temperature endpoint not yet reverse-engineered.
        _LOGGER.warning(
            "set_room_target_temperature called for room=%s temp=%s — "
            "setpoint endpoint is not yet implemented",
            call.data.get("room_id"),
            call.data.get("temperature"),
        )

    hass.services.async_register(DOMAIN, SERVICE_NETWORK_HEAL, _heal)
    hass.services.async_register(DOMAIN, SERVICE_START_INCLUSION, _inc)
    hass.services.async_register(DOMAIN, SERVICE_START_EXCLUSION, _exc)
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_DEVICE,
        _rm,
        schema=vol.Schema({vol.Required("device_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ROOM_TARGET_TEMPERATURE,
        _set_target,
        schema=vol.Schema(
            {
                vol.Required("room_id"): vol.Coerce(int),
                vol.Required("temperature"): vol.Coerce(float),
            }
        ),
    )
