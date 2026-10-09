"""Number platform for Marstek devices."""

from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MarstekConfigEntry
from .entity import MarstekEntity
from .helpers import supports_sys

PARALLEL_UPDATES = 1


NUMBER_DESCRIPTIONS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="passive_power",
        translation_key="passive_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=-2500,
        native_max_value=2500,
        native_step=50,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="passive_duration",
        translation_key="passive_duration",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=60,
        native_max_value=86400,
        native_step=60,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)

DOD = NumberEntityDescription(
    key="dod",
    translation_key="dod",
    native_unit_of_measurement=PERCENTAGE,
    native_min_value=30,
    native_max_value=88,
    native_step=1,
    mode=NumberMode.BOX,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MarstekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Marstek passive mode settings."""
    coordinator = config_entry.runtime_data
    entities: list[RestoreNumber] = [
        MarstekPassiveNumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    ]
    if supports_sys(coordinator.device_info.version):
        entities.append(MarstekDodNumber(coordinator, DOD))
    async_add_entities(entities)


class MarstekPassiveNumber(MarstekEntity, RestoreNumber):
    """Passive mode setting, applied immediately while in passive mode."""

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last value."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and (
            last.native_value is not None
        ):
            setattr(
                self.coordinator, self.entity_description.key, int(last.native_value)
            )

    @property
    @override
    def native_value(self) -> float:
        """Return the stored setting."""
        return getattr(self.coordinator, self.entity_description.key)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Store the setting and apply it when passive mode is active."""
        setattr(self.coordinator, self.entity_description.key, int(value))
        if self.coordinator.data.status.device_mode == "passive":
            await self.coordinator.async_set_mode("passive")
        self.async_write_ha_state()


class MarstekDodNumber(MarstekPassiveNumber):
    """Depth of discharge; shows the last written value since the API cannot read it."""

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the depth of discharge to the device."""
        await self.coordinator.async_set_dod(int(value))
        self.async_write_ha_state()
