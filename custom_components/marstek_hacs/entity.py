"""Base entity for Marstek devices."""

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.translation import async_get_cached_translations
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MarstekDataUpdateCoordinator
from .helpers import model_name


class MarstekEntity(CoordinatorEntity[MarstekDataUpdateCoordinator]):
    """Base class for Marstek entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the Marstek entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        device_info = coordinator.device_info
        self._attr_unique_id = f"{device_info.stable_id}_{entity_description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_info.stable_id)},
            "name": f"Marstek {model_name(device_info.device_type)}",
            "manufacturer": "Marstek",
            "model": model_name(device_info.device_type),
            "model_id": device_info.device_type,
            "sw_version": str(device_info.version),
        }

    @property
    def suggested_object_id(self) -> str | None:
        """Return the English name so entity IDs match across languages."""
        return async_get_cached_translations(self.hass, "en", "entity", DOMAIN).get(
            f"component.{DOMAIN}.entity.{self.platform.domain}"
            f".{self.entity_description.translation_key}.name"
        )
