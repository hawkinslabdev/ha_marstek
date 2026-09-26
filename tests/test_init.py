"""Tests for Marstek setup, availability, and repairs."""

from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .conftest import HOST
from custom_components.marstek.const import DOMAIN, UNREACHABLE_POLLS
from custom_components.marstek.coordinator import SCAN_INTERVAL


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_unreachable_repair(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    udp_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A repair issue appears after repeated silent polls and clears on recovery."""
    issue_id = f"open_api_unreachable_{init_integration.entry_id}"
    status = udp_client.get_device_status.return_value
    udp_client.get_device_status.side_effect = TimeoutError

    for _ in range(UNREACHABLE_POLLS - 1):
        await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    assert (
        hass.states.get("sensor.marstek_venus_e_3_0_battery_level").state
        == "unavailable"
    )

    await _poll(hass, freezer)
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue.translation_placeholders == {"host": HOST}

    udp_client.get_device_status.side_effect = None
    udp_client.get_device_status.return_value = status
    await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
