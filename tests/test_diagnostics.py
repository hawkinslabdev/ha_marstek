"""Tests for Marstek diagnostics."""

from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant

from custom_components.marstek_hacs.coordinator import SCAN_INTERVAL


@pytest.mark.parametrize("es_status", [{"bat_cap": 5120, "wifi_mac": "aabbccddeeff"}])
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """Diagnostics include raw responses with identifiers redacted."""
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    assert result["raw"]["ES.GetStatus"]["bat_cap"] == 5120
    assert result["raw"]["ES.GetStatus"]["wifi_mac"] == "**REDACTED**"
    assert result["device_info"]["wifi_mac"] == "**REDACTED**"
    assert result["device_info"]["device_type"] == "VNSE3-0"
    assert result["domain"] == "marstek_hacs"
    assert result["last_update"] is not None


async def test_diagnostics_poll_counters(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    udp_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Diagnostics count every poll and every failed poll since setup."""
    udp_client.get_device_status.side_effect = TimeoutError
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    assert result["polls_total"] == 2
    assert result["polls_failed_total"] == 1
