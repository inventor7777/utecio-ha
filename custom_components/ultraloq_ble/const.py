"""Constants for Ultraloq Bluetooth."""
import asyncio
import logging

from aiohttp.client_exceptions import ClientConnectionError

from homeassistant.const import Platform

LOGGER = logging.getLogger(__package__)

DEFAULT_SCAN_INTERVAL = 300
DOMAIN = "ultraloq_ble"
PLATFORMS = [Platform.LOCK, Platform.SENSOR, Platform.NUMBER]

DEFAULT_NAME = "Ultraloq Bluetooth"
TIMEOUT = 20
CONF_API_DEVICES = "api_devices"
SERVICE_REFRESH_LOCKS = "refresh_locks"

UL_ERRORS = (asyncio.TimeoutError, ClientConnectionError)

CONF_ZONE_METHOD = "zone_method"
DEFAULT_ZONE_METHOD = "Utec"
ZONE_METHODS = ["Utec", "Home Assistant"]

UPDATE_LISTENER = "update_listener"
UTEC_LOCKDATA = "utec_data"
