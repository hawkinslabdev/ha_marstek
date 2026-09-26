"""Diagnostics support for Marstek."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant

from .const import CONF_BLE_MAC, CONF_WIFI_MAC, CONF_WIFI_NAME, OPEN_API_REVISION
from .coordinator import MarstekConfigEntry

TO_REDACT = {CONF_MAC, CONF_BLE_MAC, CONF_WIFI_MAC, CONF_WIFI_NAME, "src"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MarstekConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return async_redact_data(
        {
            "entry": entry.as_dict(),
            "device_info": asdict(coordinator.device_info),
            "status": asdict(coordinator.data.status),
            "raw": coordinator.udp_client.results.get(coordinator.device_ip, {}),
            "failed_polls": coordinator.failed_polls,
            "error_state": coordinator.error_state,
            "open_api_revision": OPEN_API_REVISION,
        },
        TO_REDACT,
    )
