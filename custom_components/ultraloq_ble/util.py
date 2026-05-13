"""Utilities for Ultraloq Bluetooth Integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import LOGGER, UL_ERRORS
from .utecio.api import InvalidCredentials, InvalidResponse, UtecClient


async def async_validate_api(hass: HomeAssistant, email: str, password: str) -> bool:
    """Get data from API."""

    client = UtecClient(
        email=email, password=password, session=async_get_clientsession(hass)
    )

    locks = await async_fetch_api_devices(hass, email, password)
    if not locks:
        LOGGER.error("Could not retrieve any locks from Utec servers")
        raise NoDevicesError
    else:
        return True


async def async_fetch_api_devices(
    hass: HomeAssistant, email: str, password: str
) -> list[dict[str, Any]]:
    """Fetch raw device metadata from the UTEC cloud API."""

    client = UtecClient(
        email=email, password=password, session=async_get_clientsession(hass)
    )

    try:
        return await client.get_json()
    except UL_ERRORS as err:
        LOGGER.error("Failed to get information from UTEC servers: %s", err)
        raise ConnectionError from err
    except InvalidCredentials as err:
        LOGGER.error("Failed to login to UTEC servers: %s", err)
        raise
    except InvalidResponse as err:
        LOGGER.error("Received an unexpected response from UTEC servers: %s", err)
        raise ConnectionError from err


class NoDevicesError(Exception):
    """No Locks from UTECIO API."""
