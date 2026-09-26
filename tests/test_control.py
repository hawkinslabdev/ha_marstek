"""Tests for Marstek mode control."""

from unittest.mock import MagicMock

from aiomarstek import MarstekDeviceStatus
import pytest

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

SELECT = "select.marstek_vnse3_0_v147_operating_mode"
POWER = "number.marstek_vnse3_0_v147_passive_power"
DURATION = "number.marstek_vnse3_0_v147_passive_duration"


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
