"""Constants for the Marstek integration."""

from typing import Final

DOMAIN: Final = "marstek_hacs"

DEFAULT_PORT: Final = 30000
SCAN_PORTS: Final = range(49152, 65536)
UNAVAILABLE_POLLS: Final = 3
UNREACHABLE_POLLS: Final = 10
OPEN_API_REVISION: Final = "3.1"

CONF_BLE_MAC: Final = "ble_mac"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_VERSION: Final = "version"
CONF_WIFI_MAC: Final = "wifi_mac"
CONF_WIFI_NAME: Final = "wifi_name"

SUPPORTED_DEVICE_TYPES: Final[dict[str, str]] = {
    "VNSA-0": "Venus A",
    "VenusA": "Venus A",
    "Venus A": "Venus A",
    "VNSD-0": "Venus D",
    "VenusD": "Venus D",
    "Venus D": "Venus D",
    "VNSE3-0": "Venus E 3.0",
    "VenusE 3.0": "Venus E 3.0",
    "Venus E 3.0": "Venus E 3.0",
}

PV_STATE_OPTIONS: Final = ("standby", "working")
DEVICE_MODE_OPTIONS: Final = ("auto", "ai", "manual", "passive", "ups")
SELECTABLE_MODES: Final = ("auto", "ai", "passive", "ups")
BATTERY_STATUS_OPTIONS: Final = ("discharging", "charging", "idle")
PV_MODELS: Final = ("Venus A", "Venus D")
ERROR_STATE_OPTIONS: Final = ("none", "no_response", "network_error", "invalid_data")
