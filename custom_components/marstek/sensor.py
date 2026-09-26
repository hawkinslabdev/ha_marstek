"""Sensor platform for Marstek devices."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import override

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    BATTERY_STATUS_OPTIONS,
    DEVICE_MODE_OPTIONS,
    DOMAIN,
    PV_MODELS,
    PV_STATE_OPTIONS,
)
from .coordinator import MarstekConfigEntry, MarstekData
from .entity import MarstekEntity
from .helpers import (
    battery_flow_power,
    battery_status,
    es_number,
    model_name,
    stored_energy,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MarstekSensorEntityDescription(SensorEntityDescription):
    """Describe a Marstek sensor entity."""

    value_fn: Callable[[MarstekData], StateType] | None = None


def _pv_sensor_descriptions() -> tuple[MarstekSensorEntityDescription, ...]:
    """Build sensors for each of the device's four PV input channels."""
    descriptions: list[MarstekSensorEntityDescription] = []
    for pv_channel in range(1, 5):
        for metric, device_class, unit, icon in (
            (
                "power",
                SensorDeviceClass.POWER,
                UnitOfPower.WATT,
                "mdi:solar-power",
            ),
            (
                "voltage",
                SensorDeviceClass.VOLTAGE,
                UnitOfElectricPotential.VOLT,
                "mdi:flash",
            ),
            (
                "current",
                SensorDeviceClass.CURRENT,
                UnitOfElectricCurrent.AMPERE,
                "mdi:current-ac",
            ),
            (
                "state",
                SensorDeviceClass.ENUM,
                None,
                "mdi:state-machine",
            ),
        ):
            key = f"pv{pv_channel}_{metric}"
            descriptions.append(
                MarstekSensorEntityDescription(
                    key=key,
                    translation_key=key,
                    device_class=device_class,
                    native_unit_of_measurement=unit,
                    icon=icon,
                    state_class=(
                        SensorStateClass.MEASUREMENT if metric != "state" else None
                    ),
                    options=list(PV_STATE_OPTIONS) if metric == "state" else None,
                )
            )
    return tuple(descriptions)


SENSOR_DESCRIPTIONS: tuple[MarstekSensorEntityDescription, ...] = (
    MarstekSensorEntityDescription(
        key="battery_soc",
        translation_key="battery_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MarstekSensorEntityDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MarstekSensorEntityDescription(
        key="battery_charge_power",
        translation_key="battery_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: battery_flow_power(data.status, "charging"),
    ),
    MarstekSensorEntityDescription(
        key="battery_discharge_power",
        translation_key="battery_discharge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: battery_flow_power(data.status, "discharging"),
    ),
    MarstekSensorEntityDescription(
        key="battery_energy_in",
        translation_key="battery_energy_in",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: es_number(data, "total_grid_input_energy"),
    ),
    MarstekSensorEntityDescription(
        key="battery_energy_out",
        translation_key="battery_energy_out",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: es_number(data, "total_grid_output_energy"),
    ),
    MarstekSensorEntityDescription(
        key="stored_energy",
        translation_key="stored_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=stored_energy,
    ),
    MarstekSensorEntityDescription(
        key="device_mode",
        translation_key="device_mode",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:cog",
        options=list(DEVICE_MODE_OPTIONS),
    ),
    MarstekSensorEntityDescription(
        key="battery_status",
        translation_key="battery_status",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:battery",
        options=list(BATTERY_STATUS_OPTIONS),
        value_fn=lambda data: battery_status(data.status),
    ),
)

PV_SENSOR_DESCRIPTIONS: tuple[MarstekSensorEntityDescription, ...] = (
    MarstekSensorEntityDescription(
        key="total_pv_energy",
        translation_key="total_pv_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    *_pv_sensor_descriptions(),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MarstekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Marstek sensors based on a config entry."""
    coordinator = config_entry.runtime_data.coordinator
    device_ip = coordinator.device_ip
    _LOGGER.debug("Setting up Marstek sensors: %s", device_ip)

    descriptions = SENSOR_DESCRIPTIONS
    if model_name(coordinator.device_info.device_type) in PV_MODELS:
        descriptions += PV_SENSOR_DESCRIPTIONS
    else:
        registry = er.async_get(hass)
        for description in PV_SENSOR_DESCRIPTIONS:
            unique_id = f"{coordinator.device_info.stable_id}_{description.key}"
            if entity_id := registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, unique_id
            ):
                registry.async_remove(entity_id)

    sensors = [MarstekSensor(coordinator, description) for description in descriptions]

    _LOGGER.debug("Device %s sensors set up, total %d", device_ip, len(sensors))
    async_add_entities(sensors)


class MarstekSensor(MarstekEntity, SensorEntity):
    """Representation of a Marstek sensor."""

    entity_description: MarstekSensorEntityDescription

    @property
    @override
    def native_value(self) -> StateType | None:
        """Return the state of the sensor."""
        if value_fn := self.entity_description.value_fn:
            return value_fn(self.coordinator.data)
        return self.coordinator.data.status.get_value(self.entity_description.key)
