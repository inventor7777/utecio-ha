"""Button platform for Ultraloq integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UTEC_LOCKDATA
from .utecio.ble.device import UtecBleDeviceError, UtecBleNotFoundError
from .utecio.ble.lock import UtecBleLock


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ultraloq buttons for a config entry."""

    locks: list[UtecBleLock] = hass.data[DOMAIN][entry.entry_id][UTEC_LOCKDATA]
    async_add_entities(UltraloqRescanButton(lock) for lock in locks)


class UltraloqRescanButton(ButtonEntity):
    """Button entity to force an immediate BLE refresh for one lock."""

    _attr_has_entity_name = True
    _attr_name = "Rescan"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, lock: UtecBleLock) -> None:
        """Initialize the button entity."""

        self.lock = lock
        self._attr_unique_id = f"ul_{self.lock.mac_uuid}_rescan"

    @property
    def available(self) -> bool:
        """Keep the rescan button available even if the lock is offline."""

        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this lock."""

        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self.lock.mac_uuid)},
            "connections": {
                (
                    CONNECTION_BLUETOOTH,
                    device_registry.format_mac(self.lock.mac_uuid),
                )
            },
            "name": self.lock.name,
            "manufacturer": "U-tec",
            "model": self.lock.model or "Ultraloq Lock",
        }
        if self.lock.sn:
            info["serial_number"] = self.lock.sn
        return info

    async def async_press(self) -> None:
        """Force an immediate state refresh from the lock."""

        try:
            await self.lock.async_update_status()
        except (UtecBleDeviceError, UtecBleNotFoundError) as err:
            raise HomeAssistantError(
                f"Failed to rescan {self.lock.name}: {err}"
            ) from err

        for callback_func in list(getattr(self.lock, "_ha_state_callbacks", [])):
            callback_func()
