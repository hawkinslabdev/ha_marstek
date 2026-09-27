"""Data update coordinator for Marstek devices."""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import logging
from typing import Any, override

from aiomarstek import MarstekDeviceInfo, MarstekDeviceStatus

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_PORT,
    DOMAIN,
    OPEN_API_REVISION,
    REQUEST_TIMEOUT,
    SUPPORTED_DEVICE_TYPES,
    UNAVAILABLE_POLLS,
    UNREACHABLE_POLLS,
)
from .helpers import (
    MarstekClient,
    error_reason,
    error_state,
    hold_glitches,
    mode_config,
    model_name,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarstekData:
    """Normalized status plus the raw ES.GetStatus result."""

    status: MarstekDeviceStatus
    es: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class MarstekRuntimeData:
    """Runtime data for a Marstek config entry."""

    coordinator: MarstekDataUpdateCoordinator


type MarstekConfigEntry = ConfigEntry[MarstekRuntimeData]


class MarstekDataUpdateCoordinator(DataUpdateCoordinator[MarstekData]):
    """Per-device data update coordinator."""

    config_entry: MarstekConfigEntry
    device_info: MarstekDeviceInfo
    passive_power: int = 0
    passive_duration: int = 3600
    failed_polls: int = 0
    polls_total: int = 0
    polls_failed_total: int = 0
    error_state: str = "none"
    last_update: datetime | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: MarstekConfigEntry,
        udp_client: MarstekClient,
    ) -> None:
        """Initialize the coordinator."""
        self.device_ip = config_entry.data[CONF_HOST]
        self.port = config_entry.data.get(CONF_PORT, DEFAULT_PORT)
        self.udp_client = udp_client
        self.io_lock = asyncio.Lock()
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"Marstek {self.device_ip}:{self.port}",
            update_interval=SCAN_INTERVAL,
        )
        _LOGGER.debug(
            "Device %s polling coordinator started, interval: %ss",
            self.device_ip,
            SCAN_INTERVAL.total_seconds(),
        )

    @override
    async def _async_setup(self) -> None:
        """Validate device availability and cache its device information."""
        try:
            device_info = await self.udp_client.get_device_info(self.device_ip)
        except (TimeoutError, OSError, TypeError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="device_connection_failed",
                translation_placeholders={"host": self.device_ip},
            ) from err

        if not device_info.stable_id:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="missing_stable_id",
                translation_placeholders={"host": self.device_ip},
            )

        if device_info.device_type not in SUPPORTED_DEVICE_TYPES:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="unsupported_device",
                translation_placeholders={"device_type": device_info.device_type},
            )

        self.device_info = device_info
        _LOGGER.info(
            "Marstek %s (%s) firmware v%s at %s:%s, Open API rev %s",
            model_name(device_info.device_type),
            device_info.device_type,
            device_info.version,
            self.device_ip,
            self.port,
            OPEN_API_REVISION,
        )

    @property
    def issue_id(self) -> str:
        """Return the repair issue id for an unreachable Open API."""
        return f"open_api_unreachable_{self.config_entry.entry_id}"

    @override
    async def _async_update_data(self) -> MarstekData:
        """Fetch device data from the Marstek client library."""
        _LOGGER.debug("Start polling device: %s", self.device_ip)
        previous = self.data

        if self.udp_client.is_polling_paused(self.device_ip):
            _LOGGER.debug(
                "Polling paused for device: %s, skipping update", self.device_ip
            )
            return previous or MarstekData(
                status=MarstekDeviceStatus(device_ip=self.device_ip)
            )

        self.polls_total += 1
        try:
            async with self.io_lock:
                status = await self.udp_client.get_device_status(
                    self.device_ip,
                    previous_data=previous.status if previous else None,
                    timeout=REQUEST_TIMEOUT,
                )
        except (TimeoutError, OSError, TypeError) as err:
            self.failed_polls += 1
            self.polls_failed_total += 1
            if (state := error_state(err)) != self.error_state:
                self.error_state = state
                self.async_update_listeners()
            if self.failed_polls == UNREACHABLE_POLLS:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    self.issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="open_api_unreachable",
                    translation_placeholders={"host": self.device_ip},
                )
            if previous and self.failed_polls < UNAVAILABLE_POLLS:
                _LOGGER.debug(
                    "Device %s missed poll %s: %s",
                    self.device_ip,
                    self.failed_polls,
                    error_reason(err),
                )
                return previous
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="device_update_failed",
                translation_placeholders={
                    "host": f"{self.device_ip}:{self.port}",
                    "reason": error_reason(err),
                },
            ) from err

        if self.failed_polls >= UNREACHABLE_POLLS:
            ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        if self.failed_polls:
            await self._async_refresh_firmware()
        self.failed_polls = 0
        self.error_state = "none"
        self.last_update = dt_util.utcnow()
        es = self.udp_client.results.get(self.device_ip, {}).get("ES.GetStatus", {})
        return hold_glitches(previous, MarstekData(status=status, es=es))

    async def _async_refresh_firmware(self) -> None:
        """Re-read the firmware version after an outage, which a firmware update causes."""
        # ponytail: a reboot shorter than one poll interval goes unnoticed until reload
        try:
            async with self.io_lock:
                info = await self.udp_client.get_device_info(self.device_ip)
        except TimeoutError, OSError, TypeError:
            return
        if info.version == self.device_info.version:
            return
        self.device_info = replace(self.device_info, version=info.version)
        registry = dr.async_get(self.hass)
        if device := registry.async_get_device_by_identifier(
            (DOMAIN, self.device_info.stable_id), self.config_entry.entry_id
        ):
            registry.async_update_device(device.id, sw_version=str(info.version))

    async def async_set_mode(self, mode: str) -> None:
        """Switch the operating mode, applying passive settings when relevant."""
        config = mode_config(mode, self.passive_power, self.passive_duration)
        try:
            async with self.io_lock:
                accepted = await self.udp_client.async_set_mode(self.device_ip, config)
        except (TimeoutError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_mode_failed",
                translation_placeholders={"host": self.device_ip},
            ) from err
        if not accepted:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_mode_rejected",
                translation_placeholders={"mode": mode},
            )
        self.async_set_updated_data(
            replace(self.data, status=replace(self.data.status, device_mode=mode))
        )
