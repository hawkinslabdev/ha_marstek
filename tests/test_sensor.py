"""Tests for the Marstek sensor platform."""

from aiomarstek import MarstekDeviceStatus
import pytest

from homeassistant.core import HomeAssistant

from .conftest import HOST

PREFIX = "sensor.marstek_vnse3_0_v147"


@pytest.mark.parametrize(
    ("device_status", "battery_power", "charge", "discharge"),
    [
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": -1200}
            ),
            "1200",
            "1200",
            "0",
        ),
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": 800}
            ),
            "800",
            "0",
            "800",
        ),
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": 0}
            ),
            "0",
            "0",
            "0",
        ),
        (MarstekDeviceStatus(device_ip=HOST), "unknown", "unknown", "unknown"),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_battery_power_split(
    hass: HomeAssistant, battery_power: str, charge: str, discharge: str
) -> None:
    """Battery power is split into charge and discharge sensors."""
    assert hass.states.get(f"{PREFIX}_battery_power").state == battery_power
    assert hass.states.get(f"{PREFIX}_battery_charge_power").state == charge
    assert hass.states.get(f"{PREFIX}_battery_discharge_power").state == discharge


@pytest.mark.parametrize(
    ("device_status", "es_status"),
    [
        (
            MarstekDeviceStatus(device_ip=HOST, battery_soc=50),
            {
                "bat_cap": 5120,
                "total_grid_input_energy": 3273,
                "total_grid_output_energy": 2548,
            },
        )
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_battery_energy(hass: HomeAssistant) -> None:
    """Energy counters and stored energy come from ES.GetStatus."""
    assert hass.states.get(f"{PREFIX}_battery_energy_in").state == "3.273"
    assert hass.states.get(f"{PREFIX}_battery_energy_out").state == "2.548"
    assert hass.states.get(f"{PREFIX}_stored_energy").state == "2.56"
