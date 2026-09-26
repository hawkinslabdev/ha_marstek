"""Select platform for Marstek devices."""

from typing import override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SELECTABLE_MODES
from .coordinator import MarstekConfigEntry
from .entity import MarstekEntity

PARALLEL_UPDATES = 1

OPERATING_MODE = SelectEntityDescription(
    key="operating_mode",
    translation_key="operating_mode",
    options=list(SELECTABLE_MODES),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MarstekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Marstek operating mode select."""
    async_add_entities(
        [MarstekModeSelect(config_entry.runtime_data.coordinator, OPERATING_MODE)]
    )


class MarstekModeSelect(MarstekEntity, SelectEntity):
    """Operating mode control."""

    @property
    @override
    def current_option(self) -> str | None:
        """Return the current operating mode when it is selectable."""
        mode = self.coordinator.data.status.device_mode
        return mode if mode in SELECTABLE_MODES else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Switch the operating mode."""
        await self.coordinator.async_set_mode(option)
