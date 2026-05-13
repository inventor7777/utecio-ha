"""Ultraloq BLE component."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_API_DEVICES,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_REFRESH_LOCKS,
    UPDATE_LISTENER,
    UTEC_LOCKDATA,
)
from .util import async_fetch_api_devices
from .utecio import known_devices
from .utecio.ble.lock import UtecBleLock


def debug_mode():
    """Is integration in debug mode."""
    return LOGGER.isEnabledFor(logging.DEBUG)


def _build_ble_devices(api_devices: list[dict[str, Any]]) -> list[UtecBleLock]:
    """Build BLE lock objects from cached API metadata."""

    devices: list[UtecBleLock] = []
    for api_device in api_devices:
        device = UtecBleLock.from_json(api_device)
        capabilities = device.capabilities
        if isinstance(capabilities, type):
            try:
                capabilities = capabilities()
            except Exception as err:
                LOGGER.warning(
                    "Failed to initialize capabilities for model %s: %s",
                    device.model,
                    err,
                )
                capabilities = None
            else:
                device.capabilities = capabilities

        if getattr(capabilities, "bluetooth", False):
            devices.append(device)
            if device.model not in known_devices:
                LOGGER.warning(
                    "Treating unknown Ultraloq model as BLE-capable: %s", device.model
                )
        else:
            LOGGER.debug("Skipping non-BLE or unknown Ultraloq model %s", device.model)

    return devices


async def _async_refresh_entry_devices(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[dict[str, Any]]:
    """Fetch and persist fresh API device metadata for one config entry."""

    api_devices = await async_fetch_api_devices(
        hass,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_API_DEVICES: api_devices},
    )
    return api_devices


async def _async_handle_refresh_locks(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Refresh cached lock metadata for all configured Ultraloq entries."""

    for entry in hass.config_entries.async_entries(DOMAIN):
        await _async_refresh_entry_devices(hass, entry)
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lock from a config entry."""

    api_devices = entry.data.get(CONF_API_DEVICES)
    if api_devices is None:
        api_devices = await _async_refresh_entry_devices(hass, entry)

    devices = _build_ble_devices(api_devices)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {UTEC_LOCKDATA: devices}

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_LOCKS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_LOCKS,
            lambda call: _async_handle_refresh_locks(hass, call),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    update_listener = entry.add_update_listener(async_update_options)
    hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER] = update_listener

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Ultraloq config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        update_listener = hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER]
        update_listener()
        del hass.data[DOMAIN][entry.entry_id]
        if not hass.data[DOMAIN]:
            del hass.data[DOMAIN]
            if hass.services.has_service(DOMAIN, SERVICE_REFRESH_LOCKS):
                hass.services.async_remove(DOMAIN, SERVICE_REFRESH_LOCKS)
    return unload_ok


# async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """ Migrate old entry. """

#     if entry.version in [1,2]:
#         if entry.version == 1:
#             email = entry.data[CONF_USERNAME]
#         else:
#             email = entry.data[CONF_EMAIL]
#         password = entry.data[CONF_PASSWORD]

#         LOGGER.debug(f'Migrate config entry unique id to {email}')
#         entry.version = 3

#         hass.config_entries.async_update_entry(
#             entry,
#             data={
#                 CONF_EMAIL: email,
#                 CONF_PASSWORD: password,
#             },
#             options={CONF_ZONE_METHOD: DEFAULT_ZONE_METHOD},
#             unique_id=email,
#         )
#     return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""

    await hass.config_entries.async_reload(entry.entry_id)
