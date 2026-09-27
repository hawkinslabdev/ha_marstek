"""The Marstek integration."""

from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.translation import async_get_translations

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import (
    MarstekConfigEntry,
    MarstekDataUpdateCoordinator,
    MarstekRuntimeData,
)
from .helpers import (
    async_acquire_client,
    async_migrate_entity_ids,
    async_release_client,
)

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MarstekConfigEntry) -> bool:
    """Set up Marstek from a config entry."""
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    try:
        udp_client = await async_acquire_client(hass, port)
    except (TimeoutError, OSError, TypeError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="udp_client_setup_failed",
        ) from err

    coordinator = MarstekDataUpdateCoordinator(hass, entry, udp_client)
    entry.runtime_data = MarstekRuntimeData(coordinator=coordinator)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady:
        await async_release_client(hass, port)
        object.__delattr__(entry, "runtime_data")
        raise

    async_migrate_entity_ids(hass, entry.entry_id, coordinator.device_info.device_type)
    await async_get_translations(hass, "en", "entity", {DOMAIN})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MarstekConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_release_client(hass, entry.runtime_data.coordinator.port)

    return unload_ok
