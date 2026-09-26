"""Fixtures for Marstek tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aiomarstek import MarstekDeviceInfo, MarstekDeviceStatus
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from custom_components.marstek.const import DOMAIN

HOST = "192.168.1.50"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the custom integration."""


@pytest.fixture
def device_info() -> MarstekDeviceInfo:
    """Return device information for a supported device."""
    return MarstekDeviceInfo.from_response(
        {"device": "VNSE3-0", "ver": 147, "wifi_mac": "aabbccddeeff"}, HOST
    )


@pytest.fixture
def device_status() -> MarstekDeviceStatus:
    """Return a default device status."""
    return MarstekDeviceStatus(device_ip=HOST)


@pytest.fixture
def es_status() -> dict[str, Any]:
    """Return the raw ES.GetStatus result."""
    return {}


@pytest.fixture
def udp_client(
    device_info: MarstekDeviceInfo,
    device_status: MarstekDeviceStatus,
    es_status: dict[str, Any],
) -> Generator[MagicMock]:
    """Patch the shared UDP client."""
    client = MagicMock()
    client.async_setup = AsyncMock()
    client.async_cleanup = AsyncMock()
    client.get_device_info = AsyncMock(return_value=device_info)
    client.get_device_status = AsyncMock(return_value=device_status)
    client.discover_devices = AsyncMock(return_value=[device_info])
    client.is_polling_paused.return_value = False
    client.results = {HOST: {"ES.GetStatus": es_status}}
    client.async_set_mode = AsyncMock(return_value=True)
    with (
        patch("custom_components.marstek.helpers.MarstekClient", return_value=client),
        patch(
            "custom_components.marstek.helpers.network.async_get_ipv4_broadcast_addresses",
            AsyncMock(return_value=[]),
        ),
    ):
        yield client


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, udp_client: MagicMock, device_info: MarstekDeviceInfo
) -> MockConfigEntry:
    """Set up the Marstek integration."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=device_info.stable_id, data={CONF_HOST: HOST}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
