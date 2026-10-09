"""Tests for the Marstek sensor platform."""

from unittest.mock import MagicMock

from aiomarstek import MarstekDeviceInfo, MarstekDeviceStatus
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons

from .conftest import HOST
from custom_components.marstek_hacs.const import DOMAIN

PREFIX = "sensor.marstek_venus_e_3_0"


@pytest.mark.parametrize(
    ("device_status", "battery_power", "status", "charge", "discharge"),
    [
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": -1200}
            ),
            "1200",
            "charging",
            "1200",
            "0",
        ),
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": 800}
            ),
            "800",
            "discharging",
            "0",
            "800",
        ),
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"ongrid_power": 0}
            ),
            "0",
            "idle",
            "0",
            "0",
        ),
        (
            MarstekDeviceStatus(device_ip=HOST),
            "unknown",
            "unknown",
            "unknown",
            "unknown",
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_battery_power_split(
    hass: HomeAssistant, battery_power: str, status: str, charge: str, discharge: str
) -> None:
    """Battery power is split into charging and discharging sensors."""
    assert hass.states.get(f"{PREFIX}_battery_power").state == battery_power
    assert hass.states.get(f"{PREFIX}_battery_status").state == status
    assert hass.states.get(f"{PREFIX}_charging_power").state == charge
    assert hass.states.get(f"{PREFIX}_discharging_power").state == discharge


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
    assert hass.states.get(f"{PREFIX}_battery_cycles").state == "0.498"


@pytest.mark.parametrize(
    ("device_status", "es_status"),
    [
        (
            MarstekDeviceStatus(device_ip=HOST).with_es_status_response(
                {"bat_soc": 0, "bat_cap": 0}
            ),
            {"bat_soc": 0, "bat_cap": 0},
        )
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_empty_battery(hass: HomeAssistant) -> None:
    """An empty battery reports 0 % and no stored energy."""
    assert hass.states.get(f"{PREFIX}_state_of_charge").state == "0"
    assert hass.states.get(f"{PREFIX}_stored_energy").state == "0.0"
    assert hass.states.get(f"{PREFIX}_battery_cycles").state == "unknown"


@pytest.mark.usefixtures("init_integration")
async def test_no_pv_entities_on_venus_e(hass: HomeAssistant) -> None:
    """Venus E has no PV inputs."""
    assert hass.states.get(f"{PREFIX}_pv1_power") is None
    assert hass.states.get(f"{PREFIX}_lifetime_pv_energy") is None


@pytest.mark.usefixtures("init_integration")
async def test_icons_from_icon_translations(hass: HomeAssistant) -> None:
    """Sensor icons are defined in icons.json."""
    icons = await async_get_icons(hass, "entity", {DOMAIN})
    sensors = icons[DOMAIN]["sensor"]
    assert sensors["battery_status"]["default"] == "mdi:battery"
    assert sensors["pv4_state"]["default"] == "mdi:state-machine"
    assert "icon" not in hass.states.get(f"{PREFIX}_battery_status").attributes


@pytest.mark.parametrize(
    "device_info",
    [
        MarstekDeviceInfo.from_response(
            {"device": "VNSA-0", "ver": 147, "wifi_mac": "aa"}, HOST
        )
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_pv_entities_on_venus_a(hass: HomeAssistant) -> None:
    """Venus A exposes PV inputs."""
    assert hass.states.get("sensor.marstek_venus_a_pv1_power") is not None
    assert hass.states.get("sensor.marstek_venus_a_lifetime_pv_energy") is not None


async def test_stale_pv_entities_removed(
    hass: HomeAssistant,
    udp_client: MagicMock,
    device_info: MarstekDeviceInfo,
    entity_registry: er.EntityRegistry,
) -> None:
    """PV entities registered by earlier versions are removed on Venus E."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=device_info.stable_id, data={CONF_HOST: HOST}
    )
    entry.add_to_hass(hass)
    stale = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{device_info.stable_id}_pv1_power",
        config_entry=entry,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get(stale.entity_id) is None


@pytest.mark.parametrize(
    "device_status", [MarstekDeviceStatus(device_ip=HOST, battery_soc=0)]
)
@pytest.mark.usefixtures("init_integration")
async def test_soc_before_es_status(hass: HomeAssistant) -> None:
    """SOC from ES.GetMode is shown before any ES.GetStatus reply."""
    assert hass.states.get(f"{PREFIX}_state_of_charge").state == "0"
