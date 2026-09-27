"""Tests for Marstek setup, availability, and repairs."""

from dataclasses import replace
from unittest.mock import MagicMock

from aiomarstek import MarstekDeviceInfo
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .conftest import HOST
from custom_components.marstek_hacs.const import (
    DOMAIN,
    UNAVAILABLE_POLLS,
    UNREACHABLE_POLLS,
)
from custom_components.marstek_hacs.coordinator import SCAN_INTERVAL

ERROR_STATE = "sensor.marstek_venus_e_3_0_error_state"
SOC = "sensor.marstek_venus_e_3_0_state_of_charge"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_missed_polls_keep_last_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    udp_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities keep their last values until several polls in a row fail."""
    udp_client.get_device_status.return_value = replace(
        udp_client.get_device_status.return_value, battery_soc=55
    )
    await _poll(hass, freezer)
    udp_client.get_device_status.side_effect = TimeoutError

    for _ in range(UNAVAILABLE_POLLS - 1):
        await _poll(hass, freezer)
    assert hass.states.get(SOC).state == "55"
    assert hass.states.get(ERROR_STATE).state == "no_response"

    await _poll(hass, freezer)
    assert hass.states.get(SOC).state == "unavailable"


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
    assert hass.states.get(SOC).state == "unavailable"

    await _poll(hass, freezer)
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue.translation_placeholders == {"host": HOST}

    udp_client.get_device_status.side_effect = None
    udp_client.get_device_status.return_value = status
    await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_error_state_and_logging(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    udp_client: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The error state sensor stays available and logs name the device address."""
    status = udp_client.get_device_status.return_value
    assert hass.states.get(ERROR_STATE).state == "none"

    udp_client.get_device_status.side_effect = TimeoutError
    for _ in range(UNAVAILABLE_POLLS):
        await _poll(hass, freezer)
    assert hass.states.get(ERROR_STATE).state == "no_response"
    assert f"{HOST}:30000" in caplog.text
    assert "no response" in caplog.text

    udp_client.get_device_status.side_effect = OSError("Network is unreachable")
    await _poll(hass, freezer)
    assert hass.states.get(ERROR_STATE).state == "network_error"

    udp_client.get_device_status.side_effect = None
    udp_client.get_device_status.return_value = status
    await _poll(hass, freezer)
    assert hass.states.get(ERROR_STATE).state == "none"
    assert f"Marstek {HOST}:30000 data recovered" in caplog.text


async def test_legacy_entity_ids_migrated(
    hass: HomeAssistant,
    udp_client: MagicMock,
    device_info: MarstekDeviceInfo,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Entity IDs carrying the raw device type and firmware are renamed."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=device_info.stable_id, data={CONF_HOST: HOST}
    )
    entry.add_to_hass(hass)
    legacy = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{device_info.stable_id}_battery_soc",
        config_entry=entry,
        suggested_object_id="marstek_vnse3_0_v147_battery_level",
    )
    custom = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{device_info.stable_id}_battery_power",
        config_entry=entry,
        suggested_object_id="my_battery_power",
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    migrated = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{device_info.stable_id}_battery_soc"
    )
    assert legacy.entity_id == "sensor.marstek_vnse3_0_v147_battery_level"
    assert migrated == "sensor.marstek_venus_e_3_0_battery_level"
    assert entity_registry.async_get(custom.entity_id) is not None
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, device_info.stable_id), entry.entry_id
    )
    assert device.name == "Marstek Venus E 3.0"
