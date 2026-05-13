# Ultraloq BLE

This is a forked Home Assistant custom integration for Ultraloq BLE locks.

I really wanted to have local control over my U-Bolt Pro locks, and the original integration was simply nonfunctional for that. So I forked it and fixed the biggest bugs, then did extensive testing and iterating with the help of Codex. This integration should have all of the original features *(plus the first class sensors)* for non U-Bolt Pro locks, plus full support for the U-Bolt Pro locks.

## Features

Entities currently exposed per lock:
- `lock`
- `sensor.battery_level`
- `sensor.autolock_time`
- `sensor.lock_mode`
- `sensor.bolt_status` when the model reports meaningful bolt status
- `number.autolock_time`

Integration service:
- `ultraloq_ble.refresh_locks` refreshes cached lock metadata from the cloud and reloads the integration.

Important Bluetooth note:
- Passive advertisement-only proxies are not enough for lock control
- Shelly Bluetooth proxy sightings can help discovery, but active GATT connectivity is what actually matters for operating the lock
- If HA decides that the advertisement is not connectable, it will cause status updates and lock controls to fail

## Install
You can install using HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=inventor7777&repository=ultraloq-ble-ha&category=integration)

Or manually:
1. Open your Home Assistant config directory.
1. Create `custom_components` if it does not already exist.
1. Copy the `custom_components/ultraloq_ble/` folder from this repository into your Home Assistant config directory.
1. Restart Home Assistant.

## Notes

### Speed and Reliability
This integration relies on a direct, active BLE connection to the lock. Ultraloq locks are VERY stingy about BLE connections, even with the offical WiFi bridge. This means that updates may fail, and the update speed will be much lower than a normal Zigbee/WiFi lock. 

### Offline-ish Behavior

This integration is designed so the cloud is used only when needed:
- first setup
- credential reauthentication
- manual lock metadata refresh

Normal operation such as:
- lock
- unlock
- state updates
- reading battery/autolock/mode values
- setting the auto-lock timer

is intended to happen locally over BLE.

### Sensors

Each lock may expose:
- `Battery Level`
- `Autolock Time`
- `Lock Mode`
- `Bolt Status`

Notes:
- `Bolt Status` is skipped for models where it is known to be useless or always unavailable
- `Autolock Time` is exposed as a duration sensor in seconds

### Known Limitations

- Bluetooth quality matters a lot. Weak or non-connectable advertisements will cause timeouts or unavailable entities. You will need active-capable Bluetooth nodes very close to each lock.
- Some lock models may still need extra command or capability tuning.
- The integration exposes the raw autolock controls. The lock seems to discard some seconds inputs, if I could find all of the accepted inputs we could add a proper selector.
- State updates after a lock or unlock are very slow and dependent on refresh interval. Perhaps there is a way to subscribe to Ultraloq BLE pushes, but I do not have the tools to reverse engineer such a thing.

### Lock shows up but will not operate

Check:
- the lock is in Bluetooth range
- your Home Assistant Bluetooth adapter or ESPHome proxy can make active connections
- the lock is not only being seen as `connectable: false`

*Full disclaimer: Most of the improvements from the original were by GPT 5.4 Codex. However, I personally use this integration and I am happy with it, so I am sharing it in case it could be useful to anyone else.*
