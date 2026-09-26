"""Helpers for the Marstek integration."""

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
import json
import re
import socket
from typing import TYPE_CHECKING, Any, override

from aiomarstek import MarstekDeviceStatus, MarstekUDPClient, command_builder

from homeassistant.components import network
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, SUPPORTED_DEVICE_TYPES

if TYPE_CHECKING:
    from .coordinator import MarstekData

MONOTONIC_STATUS_KEYS = ("total_pv_energy",)
MONOTONIC_ES_KEYS = ("total_grid_input_energy", "total_grid_output_energy")
NONZERO_ES_KEYS = ("bat_cap",)
SOC_GLITCH_FLOOR = 10
API_MODES = {"auto": "Auto", "ai": "AI", "passive": "Passive", "ups": "UPS"}


def _next_request_id() -> int:
    command_builder._request_id = command_builder._request_id % 0xFFFF + 1
    return command_builder._request_id


command_builder.get_next_request_id = _next_request_id


class MarstekClient(MarstekUDPClient):
    """UDP client bound to the device's Open API port."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the client with a per-device store of raw results."""
        super().__init__(*args, **kwargs)
        self.results: dict[str, dict[str, dict[str, Any]]] = {}
        self._answered: set[str] = set()

    @override
    async def send_request(
        self, message: str, target_ip: str, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a request and keep its raw result per device and method."""
        response = await super().send_request(message, target_ip, *args, **kwargs)
        if isinstance(result := response.get("result"), dict):
            method = json.loads(message)["method"]
            self.results.setdefault(target_ip, {})[method] = result
            self._answered.add(target_ip)
        return response

    @override
    async def get_device_status(
        self, device_ip: str, **kwargs: Any
    ) -> MarstekDeviceStatus:
        """Fetch status, raising when the device answered none of the requests."""
        self._answered.discard(device_ip)
        status = await super().get_device_status(device_ip, **kwargs)
        if device_ip not in self._answered:
            raise TimeoutError(f"No response from {device_ip}")
        return status

    async def async_set_mode(self, device_ip: str, config: dict[str, Any]) -> bool:
        """Send ES.SetMode and return whether the device accepted it."""
        response = await self.send_request_with_polling_control(
            command_builder.build_command("ES.SetMode", {"id": 0, "config": config}),
            device_ip,
        )
        result = response.get("result")
        return isinstance(result, dict) and result.get("set_result") is True

    @override
    async def async_setup(self) -> None:
        """Bind the socket to the configured port, where the firmware replies."""
        if self._socket is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        try:
            sock.bind(("0.0.0.0", self._port))
        except OSError:
            sock.close()
            raise
        self._socket = sock

    @override
    async def send_broadcast_request(
        self, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Drop stale responses whose wrapped request id could match the broadcast."""
        self._response_cache.clear()
        return await super().send_broadcast_request(*args, **kwargs)


@dataclass(slots=True, kw_only=True)
class MarstekSharedClient:
    """A UDP client shared by every user of one Open API port."""

    udp_client: MarstekClient
    users: int = 0


MARSTEK_CLIENTS: HassKey[dict[int, MarstekSharedClient]] = HassKey(DOMAIN)


async def async_acquire_client(hass: HomeAssistant, port: int) -> MarstekClient:
    """Return the shared client for a port, creating it on first use."""
    clients = hass.data.setdefault(MARSTEK_CLIENTS, {})
    if (shared := clients.get(port)) is None:
        client = MarstekClient(port=port)
        try:
            await client.async_setup()
            addresses = await network.async_get_ipv4_broadcast_addresses(hass)
        except TimeoutError, OSError, TypeError:
            await client.async_cleanup()
            raise
        client.set_broadcast_addresses([str(address) for address in addresses])
        shared = clients[port] = MarstekSharedClient(udp_client=client)
    shared.users += 1
    return shared.udp_client


async def async_release_client(hass: HomeAssistant, port: int) -> None:
    """Release a shared client, closing it after its last user."""
    clients = hass.data[MARSTEK_CLIENTS]
    shared = clients[port]
    shared.users -= 1
    if shared.users == 0:
        del clients[port]
        await shared.udp_client.async_cleanup()


@asynccontextmanager
async def async_client(hass: HomeAssistant, port: int) -> AsyncIterator[MarstekClient]:
    """Borrow the shared client for a port."""
    client = await async_acquire_client(hass, port)
    try:
        yield client
    finally:
        await async_release_client(hass, port)


async def async_find_port(
    host: str, ports: Iterable[int], batch_size: int = 512, reply_wait: float = 1.0
) -> int | None:
    """Return the Open API port a device answers on, probing ports in batches."""
    loop = asyncio.get_running_loop()
    port_list = list(ports)
    for start in range(0, len(port_list), batch_size):
        sockets: dict[asyncio.Task[tuple[bytes, Any]], int] = {}
        opened: list[socket.socket] = []
        try:
            for port in port_list[start : start + batch_size]:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                opened.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setblocking(False)
                try:
                    sock.bind(("0.0.0.0", port))
                    sock.sendto(command_builder.discover().encode(), (host, port))
                except OSError:
                    continue
                sockets[asyncio.ensure_future(loop.sock_recvfrom(sock, 4096))] = port
            pending = set(sockets)
            deadline = loop.time() + reply_wait
            while pending and (remaining := deadline - loop.time()) > 0:
                done, pending = await asyncio.wait(
                    pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    with suppress(OSError, ValueError):
                        data, addr = task.result()
                        reply = json.loads(data)
                        if (
                            addr[0] == host
                            and isinstance(reply, dict)
                            and isinstance(reply.get("result"), dict)
                        ):
                            return sockets[task]
        finally:
            for task in sockets:
                task.cancel()
            await asyncio.gather(*sockets, return_exceptions=True)
            for sock in opened:
                sock.close()
    return None


def battery_status(status: MarstekDeviceStatus) -> str | None:
    """Return the battery flow direction, naming discharge as discharging."""
    return (
        "discharging" if status.battery_status == "selling" else status.battery_status
    )


def battery_flow_power(
    status: MarstekDeviceStatus, direction: str
) -> float | int | None:
    """Return battery power for one flow direction, or zero when flowing the other way."""
    if status.battery_power is None or (current := battery_status(status)) is None:
        return None
    return status.battery_power if current == direction else 0


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _held(old: object, new: object, *, monotonic: bool) -> bool:
    if not _is_number(old):
        return False
    if not _is_number(new):
        return True
    return new < old if monotonic else new == 0


def hold_glitches(previous: MarstekData | None, current: MarstekData) -> MarstekData:
    """Keep previous values where the device reports implausible zeros or drops."""
    if previous is None:
        return current
    status = current.status
    if (
        status.battery_soc == 0
        and (previous.status.battery_soc or 0) >= SOC_GLITCH_FLOOR
    ):
        status = replace(status, battery_soc=previous.status.battery_soc)
    for key in MONOTONIC_STATUS_KEYS:
        old = getattr(previous.status, key)
        if _held(old, getattr(status, key), monotonic=True):
            status = replace(status, **{key: old})
    es = dict(current.es)
    for keys, monotonic in ((MONOTONIC_ES_KEYS, True), (NONZERO_ES_KEYS, False)):
        for key in keys:
            if _held(previous.es.get(key), es.get(key), monotonic=monotonic):
                es[key] = previous.es[key]
    return replace(current, status=status, es=es)


def mode_config(mode: str, power: int, duration: int) -> dict[str, Any]:
    """Return the ES.SetMode config for an operating mode."""
    api_mode = API_MODES[mode]
    if mode == "passive":
        return {"mode": api_mode, "passive_cfg": {"power": power, "cd_time": duration}}
    return {"mode": api_mode, f"{mode}_cfg": {"enable": 1}}


def es_number(data: MarstekData, key: str) -> float | int | None:
    """Return a numeric ES.GetStatus field, or None when absent or invalid."""
    value = data.es.get(key)
    return value if _is_number(value) else None


def stored_energy(data: MarstekData) -> float | None:
    """Return stored energy in Wh from total capacity and state of charge."""
    capacity = es_number(data, "bat_cap")
    soc = data.status.battery_soc
    if capacity is None or soc is None:
        return None
    return capacity * soc / 100


def model_name(device_type: str) -> str:
    """Return the marketing model name for a reported device type."""
    return SUPPORTED_DEVICE_TYPES.get(device_type, device_type)


def error_state(err: Exception) -> str:
    """Return the error state for a failed poll."""
    if isinstance(err, TimeoutError):
        return "no_response"
    if isinstance(err, OSError):
        return "network_error"
    return "invalid_data"


def error_reason(err: Exception) -> str:
    """Return a log-friendly reason for a failed poll."""
    reason = error_state(err).replace("_", " ")
    return f"{reason} ({err})" if str(err) else reason


def async_migrate_entity_ids(
    hass: HomeAssistant, entry_id: str, device_type: str
) -> None:
    """Rename entity IDs that carry the raw device type and firmware version."""
    registry = er.async_get(hass)
    legacy = re.compile(rf"^marstek_{re.escape(slugify(device_type))}_v[^_]+_")
    prefix = f"marstek_{slugify(model_name(device_type))}_"
    for entity in er.async_entries_for_config_entry(registry, entry_id):
        domain, object_id = split_entity_id(entity.entity_id)
        new_entity_id = f"{domain}.{legacy.sub(prefix, object_id, count=1)}"
        if new_entity_id != entity.entity_id and not registry.async_is_registered(
            new_entity_id
        ):
            registry.async_update_entity(entity.entity_id, new_entity_id=new_entity_id)
