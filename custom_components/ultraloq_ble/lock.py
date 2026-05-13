"""Lock platform for Ultraloq integration."""
from __future__ import annotations

from typing import Any
from datetime import timedelta

from bleak.backends.device import BLEDevice
from .utecio.ble.lock import UtecBleLock
from .utecio.ble.device import UtecBleNotFoundError, UtecBleDeviceError
from .utecio.enums import DeviceBatteryLevel, DeviceLockStatus, DeviceLockWorkMode

from homeassistant.components import bluetooth
from homeassistant.components.lock import (
    LockEntity,
    LockEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers import device_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, UTEC_LOCKDATA, DEFAULT_SCAN_INTERVAL, LOGGER


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set Up Ultraloq Lock Entities."""

    data: list[UtecBleLock] = hass.data[DOMAIN][entry.entry_id][UTEC_LOCKDATA]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    entities = []

    for lock in data:
        add = UtecLock(hass, lock, scan_interval=scan_interval)
        entities.append(add)
    async_add_entities(new_entities=entities)


class UtecLock(LockEntity):
    """Representation of Ultraloq Device."""

    def __init__(
        self, hass: HomeAssistant, lock: UtecBleLock, scan_interval: int
    ) -> None:
        """Initialize the Lock."""
        super().__init__()
        self.lock: UtecBleLock = lock
        self._attr_is_locked = True
        self.lock.async_bledevice_callback = self.async_bledevice_callback
        self.lock._ha_available = True
        self.scaninterval = scan_interval
        self.update_track_cancel = None
        self._cancel_unavailable_track = None
        self._attributes = {}
        self._update_in_progress = False
        self._attr_supported_features = LockEntityFeature(0)
        if not hasattr(self.lock, "_ha_state_callbacks"):
            self.lock._ha_state_callbacks = []
        # uteclogger.setLevel(LOGGER.level)

    def _candidate_addresses(self) -> list[str]:
        """Return candidate BLE addresses to try for this lock."""

        candidates: list[str] = []
        for address in (self.lock.mac_uuid, self.lock.wurx_uuid):
            if address and address not in candidates:
                candidates.append(address)
        return candidates

    @property
    def should_poll(self) -> bool:
        """False if entity pushes its state to HA."""
        return False

    # @property
    # def device_info(self) -> dict[str, Any]:
    #     """Return device registry information for this entity."""

    #     return self.lock.config

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this lock."""

        identifiers = {(DOMAIN, self.lock.mac_uuid)}
        info: DeviceInfo = {
            "identifiers": identifiers,
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

    @property
    def extra_state_attributes(self):
        """Return lock state attributes."""
        if not self.lock:
            return {}

        attrs = {
            "battery_level": DeviceBatteryLevel(self.lock.battery).name,
            "autolock_time": (
                self.lock.autolock_time if self.lock.autolock_time >= 0 else -1
            ),
            "lock_status": DeviceLockStatus(self.lock.lock_status).name,
            "bolt_status": DeviceLockStatus(self.lock.bolt_status).name,
            "lock_mode": DeviceLockWorkMode(self.lock.lock_mode).name,
        }
        attrs.update(self._attributes)
        return attrs

    @property
    def unique_id(self) -> str:
        """Sets unique ID for this entity."""

        return "ul_" + device_registry.format_mac(self.lock.mac_uuid)

    @property
    def name(self) -> str:
        """Return name of the entity."""

        return self.lock.name

    def _sync_state_from_lock(self) -> None:
        """Update the entity state from the latest lock data."""

        if self.lock.lock_status == DeviceLockStatus.UNLOCKED.value:
            self._attr_is_locked = False
        elif self.lock.lock_status == DeviceLockStatus.LOCKED.value:
            self._attr_is_locked = True

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        self.lock._ha_state_callbacks.append(self._handle_lock_state_update)
        address = self.lock.wurx_uuid if self.lock.wurx_uuid else self.lock.mac_uuid
        self.async_on_remove(
            bluetooth.async_track_unavailable(
                self.hass,
                self._unavailable_callback,
                address,
                connectable=False,
            )
        )
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._available_callback,
                {"address": address},
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )
        self._attr_available = any(
            bluetooth.async_address_present(self.hass, candidate, connectable=True)
            or bluetooth.async_address_present(self.hass, candidate, connectable=False)
            for candidate in self._candidate_addresses()
        )
        self.schedule_update_lock_state(2)
        return await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass."""
        if self._handle_lock_state_update in self.lock._ha_state_callbacks:
            self.lock._ha_state_callbacks.remove(self._handle_lock_state_update)
        if self.update_track_cancel:
            self.update_track_cancel()
        return await super().async_will_remove_from_hass()

    async def async_bledevice_callback(self, device: str) -> BLEDevice | Any:
        """Return BLEDevice from HA bleak instance if available."""
        candidates = [device]
        for candidate in self._candidate_addresses():
            if candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            if ble_device := bluetooth.async_ble_device_from_address(
                self.hass, candidate, connectable=True
            ):
                return ble_device

            if service_info := bluetooth.async_last_service_info(
                self.hass, candidate, connectable=True
            ):
                return service_info.device

            if ble_device := bluetooth.async_ble_device_from_address(
                self.hass, candidate, connectable=False
            ):
                self._attributes["ble_connectable"] = False
                self._attributes["ble_seen_address"] = candidate
                LOGGER.warning(
                    "Found only non-connectable BLE advertisement for %s at %s",
                    self.lock.name,
                    candidate,
                )
                continue

            if service_info := bluetooth.async_last_service_info(
                self.hass, candidate, connectable=False
            ):
                LOGGER.warning(
                    "Found only non-connectable BLE service info for %s at %s",
                    self.lock.name,
                    candidate,
                )
                self._attributes["ble_connectable"] = False
                self._attributes["ble_seen_address"] = candidate
                self._attributes["ble_source"] = service_info.source
                continue

        normalized_requested = device.replace(":", "").lower()
        for service_info in bluetooth.async_discovered_service_info(
            self.hass, connectable=False
        ):
            if service_info.name == self.lock.name:
                self._attributes["ble_connectable"] = service_info.connectable
                self._attributes["ble_seen_address"] = service_info.address
                self._attributes["ble_source"] = service_info.source
                if service_info.connectable:
                    LOGGER.warning(
                        "Resolved Ultraloq %s by name using discovered address %s instead of %s",
                        self.lock.name,
                        service_info.address,
                        device,
                    )
                    return service_info.device
                continue

            normalized_seen = service_info.address.replace(":", "").lower()
            if normalized_seen == normalized_requested:
                self._attributes["ble_connectable"] = service_info.connectable
                self._attributes["ble_seen_address"] = service_info.address
                self._attributes["ble_source"] = service_info.source
                if service_info.connectable:
                    return service_info.device
                continue

        LOGGER.warning(
            "Home Assistant cannot currently resolve BLE device for %s. Tried addresses: %s",
            self.lock.name,
            ", ".join(candidates),
        )
        return None

    @callback
    def _unavailable_callback(self, info: bluetooth.BluetoothServiceInfoBleak) -> None:
        if self.update_track_cancel:
            self.update_track_cancel()
            self.update_track_cancel = None
        LOGGER.debug("%s unavailable.", self.lock.name)
        self._attr_available = False
        self.lock._ha_available = False
        self._notify_lock_state_listeners()
        self.async_write_ha_state()

    @callback
    def _available_callback(
        self,
        info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        self._attr_available = True
        self.lock._ha_available = True
        self._notify_lock_state_listeners()
        self.async_write_ha_state()
        self.schedule_update_lock_state(2)

    @callback
    def _handle_lock_state_update(self) -> None:
        """Handle shared lock state update callback."""
        self.async_write_ha_state()

    @callback
    def _notify_lock_state_listeners(self) -> None:
        """Notify all entities bound to this lock to refresh state."""

        for callback_func in list(self.lock._ha_state_callbacks):
            callback_func()

    def schedule_update_lock_state(self, offset: int):
        """Schedule an update from the lock."""
        if self.update_track_cancel:
            self.update_track_cancel()
            self.update_track_cancel = None
        if self._attr_available:
            self.update_track_cancel = async_call_later(
                self.hass,
                timedelta(seconds=offset),
                self._schedule_request_update,
            )

    @callback
    def _schedule_request_update(self, _now) -> None:
        """Schedule a refresh task safely from any callback context."""
        self.hass.add_job(self.request_update)

    @callback
    def request_update(self):
        """Request an update of the lock state."""
        if self.update_track_cancel:
            self.update_track_cancel()
            self.update_track_cancel = None

        if (
            self.enabled
            and self.hass
            and not self._update_staged
            and not self._update_in_progress
        ):
            self.schedule_update_ha_state(force_refresh=True)

    async def async_update(self, **kwargs):
        """Update the lock."""
        LOGGER.debug("Updating %s with scan interval: %s", self.name, self.scaninterval)
        self._update_in_progress = True
        try:
            await self.lock.async_update_status()
            self._sync_state_from_lock()
            LOGGER.info("(%s) Updated.", self.name)
        except (UtecBleDeviceError, UtecBleNotFoundError) as e:
            LOGGER.error(e)
        finally:
            self._update_in_progress = False
            self._notify_lock_state_listeners()
            self.schedule_update_lock_state(self.scaninterval)

    async def async_lock(self, **kwargs):
        """Lock the lock."""
        try:
            await self.lock.async_lock()
            await self.async_update()
            self.async_write_ha_state()
        except (UtecBleDeviceError, UtecBleNotFoundError) as e:
            LOGGER.error(e)

    async def async_unlock(self, **kwargs):
        """Unlock the lock."""
        try:
            await self.lock.async_unlock()
            await self.async_update()
            self.async_write_ha_state()
            if self.lock.capabilities.autolock and self.lock.autolock_time:
                async_call_later(
                    self.hass,
                    timedelta(seconds=self.lock.autolock_time),
                    lambda Now: self._set_state_locked(),
                )
        except (UtecBleDeviceError, UtecBleNotFoundError) as e:
            LOGGER.error(e)

    async def async_open(self, **kwargs: Any) -> None:
        """Open the door latch."""
        return await self.async_unlock(**kwargs)

    def _set_state_locked(self):
        LOGGER.debug("Autolock %s", self.name)
        self._attr_is_locked = True
        self.async_write_ha_state()
