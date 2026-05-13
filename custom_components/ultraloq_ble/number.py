"""Number platform for Ultraloq integration."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UTEC_LOCKDATA
from .utecio.ble.lock import UtecBleLock
from .utecio.ble.device import UtecBleDeviceError, UtecBleNotFoundError
from .utecio.enums import DeviceLockStatus


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ultraloq number entities for a config entry."""

    locks: list[UtecBleLock] = hass.data[DOMAIN][entry.entry_id][UTEC_LOCKDATA]
    entities: list[UltraloqAutolockNumber] = []

    for lock in locks:
        if not getattr(lock.capabilities, "autolock", False):
            continue
        if not hasattr(lock, "_ha_state_callbacks"):
            lock._ha_state_callbacks = []
        entities.append(UltraloqAutolockNumber(lock))

    async_add_entities(entities)


class UltraloqAutolockNumber(NumberEntity):
    """Number entity for the Ultraloq auto-lock timer."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Autolock Time"
    _attr_native_min_value = 0
    _attr_native_max_value = 300
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, lock: UtecBleLock) -> None:
        """Initialize the number entity."""

        self.lock = lock
        self._attr_unique_id = f"ul_{self.lock.mac_uuid}_autolock_time"

    @property
    def available(self) -> bool:
        """Return availability."""

        return (
            getattr(self.lock, "_ha_available", True)
            and self.lock.lock_status != DeviceLockStatus.NOTSET.value
        )

    @property
    def native_value(self) -> float | None:
        """Return the current auto-lock timer."""

        return self.lock.autolock_time if self.lock.autolock_time >= 0 else None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this lock."""

        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self.lock.mac_uuid)},
            "name": self.lock.name,
            "manufacturer": "U-tec",
            "model": self.lock.model or "Ultraloq Lock",
        }
        if self.lock.sn:
            info["serial_number"] = self.lock.sn
        return info

    async def async_set_native_value(self, value: float) -> None:
        """Set the auto-lock timer in seconds."""

        seconds = int(value)
        try:
            await self.lock.async_set_autolock(seconds)
        except (UtecBleDeviceError, UtecBleNotFoundError):
            raise
        else:
            self.async_write_ha_state()
            for callback_func in list(self.lock._ha_state_callbacks):
                callback_func()

    async def async_added_to_hass(self) -> None:
        """Register shared state callback."""

        self.lock._ha_state_callbacks.append(self._handle_lock_state_update)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        """Unregister shared state callback."""

        if self._handle_lock_state_update in self.lock._ha_state_callbacks:
            self.lock._ha_state_callbacks.remove(self._handle_lock_state_update)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_lock_state_update(self) -> None:
        """Handle a shared lock state update."""

        self.async_write_ha_state()
