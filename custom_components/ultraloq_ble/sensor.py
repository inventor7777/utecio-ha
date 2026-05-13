"""Sensor platform for Ultraloq integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UTEC_LOCKDATA
from .utecio.ble.lock import UtecBleLock
from .utecio.enums import DeviceBatteryLevel, DeviceLockStatus, DeviceLockWorkMode

NO_BOLT_STATUS_MODELS = {
    "U-Bolt-Pro",
    "U-Bolt-PRO",
    "U-Bolt Pro",
}


@dataclass(frozen=True, kw_only=True)
class UltraloqSensorDescription(SensorEntityDescription):
    """Description for an Ultraloq sensor."""

    value_fn: Callable[[UtecBleLock], object]


SENSORS: tuple[UltraloqSensorDescription, ...] = (
    UltraloqSensorDescription(
        key="battery_level",
        device_class=SensorDeviceClass.ENUM,
        options=[level.name for level in DeviceBatteryLevel if level.name != "NOTSET"],
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:battery-bluetooth-variant",
        value_fn=lambda lock: DeviceBatteryLevel(lock.battery).name,
    ),
    UltraloqSensorDescription(
        key="autolock_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda lock: lock.autolock_time if lock.autolock_time >= 0 else None,
    ),
    UltraloqSensorDescription(
        key="bolt_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.name for status in DeviceLockStatus],
        icon="mdi:lock-smart",
        value_fn=lambda lock: DeviceLockStatus(lock.bolt_status).name,
    ),
    UltraloqSensorDescription(
        key="lock_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[mode.name for mode in DeviceLockWorkMode],
        icon="mdi:lock-smart",
        value_fn=lambda lock: DeviceLockWorkMode(lock.lock_mode).name,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Ultraloq sensors for a config entry."""

    locks: list[UtecBleLock] = hass.data[DOMAIN][entry.entry_id][UTEC_LOCKDATA]
    entities: list[UltraloqSensor] = []

    for lock in locks:
        if not hasattr(lock, "_ha_state_callbacks"):
            lock._ha_state_callbacks = []
        for description in SENSORS:
            if (
                description.key == "bolt_status"
                and (
                    lock.model in NO_BOLT_STATUS_MODELS
                    or lock.bolt_status == DeviceLockStatus.UNAVAILABLE.value
                )
            ):
                continue
            entities.append(UltraloqSensor(lock, description))

    async_add_entities(entities)


class UltraloqSensor(SensorEntity):
    """Representation of an Ultraloq sensor."""

    entity_description: UltraloqSensorDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, lock: UtecBleLock, description: UltraloqSensorDescription
    ) -> None:
        """Initialize the sensor."""

        self.lock = lock
        self.entity_description = description
        self._attr_unique_id = (
            f"ul_{self.lock.mac_uuid}_{self.entity_description.key}"
        )
        self._attr_name = self.entity_description.key.replace("_", " ").title()

    @property
    def available(self) -> bool:
        """Return availability based on whether we've read any lock data."""

        return (
            getattr(self.lock, "_ha_available", True)
            and self.lock.lock_status != DeviceLockStatus.NOTSET.value
        )

    @property
    def native_value(self):
        """Return the sensor value."""

        return self.entity_description.value_fn(self.lock)

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
