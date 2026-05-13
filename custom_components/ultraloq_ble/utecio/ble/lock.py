import datetime

from ..enums import BLECommandCode, DeviceLockWorkMode
from ..util import to_byte_array
from .device import UtecBleDevice, UtecBleRequest


class UtecBleLock(UtecBleDevice):
    def __init__(
        self,
        uid: str,
        password: str,
        mac_uuid: str,
        device_name: str,
        wurx_uuid: str = "",
        device_model: str = "",
    ):
        super().__init__(
            uid=uid,
            password=password,
            mac_uuid=mac_uuid,
            wurx_uuid=wurx_uuid,
            device_name=device_name,
            device_model=device_model,
        )

    async def async_unlock(self, update: bool = True):
        if update:
            self.add_request(UtecBleRequest(BLECommandCode.LOCK_STATUS))
        self.add_request(UtecBleRequest(BLECommandCode.UNLOCK), priority=True)

        await self.send_requests()

    async def async_lock(self, update: bool = True):
        if update:
            self.add_request(UtecBleRequest(BLECommandCode.LOCK_STATUS))
        self.add_request(UtecBleRequest(BLECommandCode.BOLT_LOCK), priority=True)

        await self.send_requests()

    async def async_reboot(self) -> bool:
        self.add_request(UtecBleRequest(BLECommandCode.REBOOT))
        return await self.send_requests()

    async def async_set_workmode(self, mode: DeviceLockWorkMode):
        self.add_request(UtecBleRequest(BLECommandCode.ADMIN_LOGIN))
        if self.capabilities.bt264:
            self.add_request(
                UtecBleRequest(BLECommandCode.SET_LOCK_STATUS, data=bytes([mode.value]))
            )
        else:
            self.add_request(
                UtecBleRequest(BLECommandCode.SET_WORK_MODE, data=bytes([mode.value]))
            )

        await self.send_requests()

    async def async_set_autolock(self, seconds: int):
        if self.capabilities.autolock:
            self.add_request(UtecBleRequest(BLECommandCode.ADMIN_LOGIN))
            self.add_request(
                UtecBleRequest(
                    BLECommandCode.SET_AUTOLOCK,
                    data=to_byte_array(seconds, 2) + bytes([0]),
                )
            )
        await self.send_requests()

    async def async_update_status(self):
        self.debug("(%s) %s - Updating lock data...", self.mac_uuid, self.name)
        self.add_request(UtecBleRequest(BLECommandCode.ADMIN_LOGIN))
        self.add_request(UtecBleRequest(BLECommandCode.LOCK_STATUS))
        if not self.capabilities.bt264:
            self.add_request(UtecBleRequest(BLECommandCode.GET_LOCK_STATUS))
            self.add_request(UtecBleRequest(BLECommandCode.GET_BATTERY))
            self.add_request(UtecBleRequest(BLECommandCode.GET_MUTE))

        if self.capabilities.autolock:
            self.add_request(UtecBleRequest(BLECommandCode.GET_AUTOLOCK))

        # self.add_request(BleRequest(device=self, command=BLECommandCode.READ_TIME))
        await self.send_requests()
        self.debug("(%s) %s - Update Successful.", self.mac_uuid, self.name)
