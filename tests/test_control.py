"""Tests for Marstek mode control."""

import asyncio
from unittest.mock import MagicMock

from aiomarstek import MarstekDeviceInfo, MarstekDeviceStatus
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import HOST
from custom_components.marstek_hacs.coordinator import SCAN_INTERVAL

SELECT = "select.marstek_venus_e_3_0_operating_mode"
POWER = "number.marstek_venus_e_3_0_passive_power"
DURATION = "number.marstek_venus_e_3_0_passive_duration"
DOD = "number.marstek_venus_e_3_0_depth_of_discharge"


def _info(version: int | str) -> MarstekDeviceInfo:
    return MarstekDeviceInfo.from_response(
        {"device": "VNSE3-0", "ver": version, "wifi_mac": "aabbccddeeff"}, HOST
    )


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT, ATTR_OPTION: option},
        blocking=True,
    )


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


@pytest.mark.parametrize(
    "device_status", [MarstekDeviceStatus(device_ip=HOST, device_mode="auto")]
)
@pytest.mark.usefixtures("init_integration")
async def test_select_passive_uses_numbers(
    hass: HomeAssistant, udp_client: MagicMock
) -> None:
    """Selecting passive mode sends the configured power and duration."""
    assert hass.states.get(SELECT).state == "auto"
    await _set(hass, POWER, -1200)
    await _set(hass, DURATION, 900)
    udp_client.async_set_mode.assert_not_called()

    await _select(hass, "passive")
    udp_client.async_set_mode.assert_called_once_with(
        HOST, {"mode": "Passive", "passive_cfg": {"power": -1200, "cd_time": 900}}
    )


@pytest.mark.parametrize(
    "device_status", [MarstekDeviceStatus(device_ip=HOST, device_mode="passive")]
)
@pytest.mark.usefixtures("init_integration")
async def test_number_resends_in_passive_mode(
    hass: HomeAssistant, udp_client: MagicMock
) -> None:
    """Changing passive power while in passive mode applies it immediately."""
    await _set(hass, POWER, 500)
    udp_client.async_set_mode.assert_called_once_with(
        HOST, {"mode": "Passive", "passive_cfg": {"power": 500, "cd_time": 3600}}
    )


@pytest.mark.usefixtures("init_integration")
async def test_set_mode_rejected(hass: HomeAssistant, udp_client: MagicMock) -> None:
    """A rejected mode change raises an error."""
    udp_client.async_set_mode.return_value = False
    with pytest.raises(HomeAssistantError):
        await _select(hass, "ai")


@pytest.mark.parametrize(
    "device_status", [MarstekDeviceStatus(device_ip=HOST, device_mode="manual")]
)
@pytest.mark.usefixtures("init_integration")
async def test_select_manual_mode_unknown(hass: HomeAssistant) -> None:
    """Manual mode is app-scheduled and not selectable."""
    assert hass.states.get(SELECT).state == "unknown"


async def test_set_mode_waits_for_poll(
    hass: HomeAssistant, init_integration: MockConfigEntry, udp_client: MagicMock
) -> None:
    """ES.SetMode is sent only after an in-flight poll finishes."""
    coordinator = init_integration.runtime_data
    status = udp_client.get_device_status.return_value
    release = asyncio.Event()

    async def slow_poll(*_args: object, **_kwargs: object) -> MarstekDeviceStatus:
        await release.wait()
        return status

    udp_client.get_device_status.side_effect = slow_poll
    poll = hass.async_create_task(coordinator.async_refresh())
    await asyncio.sleep(0)
    select = hass.async_create_task(_select(hass, "ai"))
    await asyncio.sleep(0)
    udp_client.async_set_mode.assert_not_called()

    release.set()
    await poll
    await select
    udp_client.async_set_mode.assert_called_once()


@pytest.mark.parametrize(
    "device_status", [MarstekDeviceStatus(device_ip=HOST, device_mode="passive")]
)
async def test_reload_does_not_send_mode(
    hass: HomeAssistant,
    udp_client: MagicMock,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Restored passive settings and polling never write to the device."""
    await _set(hass, POWER, 500)
    udp_client.async_set_mode.reset_mock()

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    for _ in range(3):
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert hass.states.get(POWER).state == "500"
    udp_client.async_set_mode.assert_not_called()


@pytest.mark.parametrize("device_info", [_info(149), _info("unknown")])
@pytest.mark.usefixtures("init_integration")
async def test_no_dod_below_firmware_150(hass: HomeAssistant) -> None:
    """Depth of discharge needs firmware 150 or an unparseable version is skipped."""
    assert hass.states.get(DOD) is None


@pytest.mark.parametrize("device_info", [_info(150), _info("150.9")])
@pytest.mark.usefixtures("init_integration")
async def test_dod_from_firmware_150(
    hass: HomeAssistant, udp_client: MagicMock
) -> None:
    """Depth of discharge defaults to 88 and is written with DOD.SET."""
    assert hass.states.get(DOD).state == "88"
    udp_client.async_set_dod.assert_not_called()

    await _set(hass, DOD, 70)
    udp_client.async_set_dod.assert_called_once_with(HOST, 70)
    assert hass.states.get(DOD).state == "70"


@pytest.mark.parametrize("device_info", [_info(150)])
@pytest.mark.usefixtures("init_integration")
async def test_dod_rejected(hass: HomeAssistant, udp_client: MagicMock) -> None:
    """A rejected depth of discharge raises an error and keeps the old value."""
    udp_client.async_set_dod.return_value = False
    with pytest.raises(HomeAssistantError):
        await _set(hass, DOD, 70)
    assert hass.states.get(DOD).state == "88"
