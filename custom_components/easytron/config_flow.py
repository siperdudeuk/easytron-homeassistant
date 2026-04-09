"""Config flow for EASYTRON."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EasytronApiError, EasytronAuthError, EasytronClient
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_HOST,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
    }
)


class EasytronConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EASYTRON."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = EasytronClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=session,
            )
            try:
                ping = await client.async_test_connection()
            except EasytronAuthError as err:
                _LOGGER.warning("EASYTRON auth failed: %s", err)
                errors["base"] = "invalid_auth"
            except EasytronApiError as err:
                _LOGGER.warning("EASYTRON connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during EASYTRON setup")
                errors["base"] = "unknown"
            else:
                unique = ping.get("uniqueid") or user_input[CONF_HOST]
                await self.async_set_unique_id(str(unique))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"EASYTRON {user_input[CONF_HOST]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
