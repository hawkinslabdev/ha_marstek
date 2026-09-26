"""Tests for the Marstek config flow."""

from unittest.mock import MagicMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import HOST
from custom_components.marstek.const import DOMAIN


async def _manual_flow(hass: HomeAssistant, user_input: dict) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_manual_default_port(hass: HomeAssistant, udp_client: MagicMock) -> None:
    """Manual setup without a port uses the default Open API port."""
    result = await _manual_flow(hass, {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PORT] == 30000


async def test_manual_finds_custom_port(
    hass: HomeAssistant, udp_client: MagicMock
) -> None:
    """Manual setup scans for the Open API port when the default does not answer."""
    device_info = udp_client.get_device_info.return_value
    udp_client.get_device_info.side_effect = [TimeoutError, device_info]
    with patch(
        "custom_components.marstek.config_flow.async_find_port", return_value=50123
    ):
        result = await _manual_flow(hass, {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PORT] == 50123


async def test_manual_explicit_port(hass: HomeAssistant, udp_client: MagicMock) -> None:
    """Manual setup with an explicit port skips the scan."""
    with patch("custom_components.marstek.config_flow.async_find_port") as find:
        result = await _manual_flow(hass, {CONF_HOST: HOST, CONF_PORT: 50200})
    find.assert_not_called()
    assert result["data"][CONF_PORT] == 50200


async def test_manual_port_not_found(
    hass: HomeAssistant, udp_client: MagicMock
) -> None:
    """Manual setup reports a connection error when no port answers."""
    udp_client.get_device_info.side_effect = TimeoutError
    with patch(
        "custom_components.marstek.config_flow.async_find_port", return_value=None
    ):
        result = await _manual_flow(hass, {CONF_HOST: HOST})
    assert result["errors"] == {"base": "cannot_connect"}
