"""Tests for Marstek diagnostics."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant


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
