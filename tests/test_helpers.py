"""Tests for Marstek helpers."""

import asyncio
import json
import socket
from unittest.mock import AsyncMock, patch

from aiomarstek import MarstekDeviceStatus, MarstekUDPClient, command_builder
import pytest

from custom_components.marstek.coordinator import MarstekData
from custom_components.marstek.helpers import (
    MarstekClient,
    async_find_port,
    hold_glitches,
    mode_config,
)

DEVICE_PORT = 50005


def test_request_id_wraps_within_16_bits() -> None:
    """Request identifiers wrap before exceeding the firmware's 16-bit field."""
    command_builder._request_id = 0xFFFF
    assert json.loads(command_builder.discover())["id"] == 1


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ({"result": {"device": "VNSE3-0"}}, DEVICE_PORT),
        (5, None),
        (["result"], None),
        ({"error": {"code": -32601}}, None),
    ],
)
async def test_find_port(reply: object, expected: int | None) -> None:
    """The scan returns the port that answers with a result object."""
    device = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    device.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    device.bind(("127.0.0.2", DEVICE_PORT))
    device.setblocking(False)
    loop = asyncio.get_running_loop()

    async def answer() -> None:
        _, addr = await loop.sock_recvfrom(device, 4096)
        await loop.sock_sendto(
            device, json.dumps(reply).encode(), (addr[0], DEVICE_PORT)
        )

    task = asyncio.create_task(answer())
    try:
        assert await async_find_port("127.0.0.2", range(50000, 50010)) == expected
    finally:
        task.cancel()
        device.close()


def test_hold_glitches() -> None:
    """Implausible drops keep the previous value; plausible changes pass."""
    previous = MarstekData(
        status=MarstekDeviceStatus(device_ip="h", battery_soc=60, total_pv_energy=500),
        es={"bat_cap": 5120, "total_grid_input_energy": 3000},
    )
    glitch = MarstekData(
        status=MarstekDeviceStatus(device_ip="h", battery_soc=0, total_pv_energy=0),
        es={"bat_cap": 0, "total_grid_input_energy": 0},
    )
    assert hold_glitches(previous, glitch) == previous

    real = MarstekData(
        status=MarstekDeviceStatus(device_ip="h", battery_soc=55, total_pv_energy=510),
        es={"bat_cap": 5120, "total_grid_input_energy": 3010},
    )
    assert hold_glitches(previous, real) == real
    assert hold_glitches(None, glitch) == glitch


def test_mode_config() -> None:
    """Mode configs follow the Open API ES.SetMode schema."""
    assert mode_config("auto", 0, 0) == {"mode": "Auto", "auto_cfg": {"enable": 1}}
    assert mode_config("ups", 0, 0) == {"mode": "UPS", "ups_cfg": {"enable": 1}}
    assert mode_config("passive", -800, 600) == {
        "mode": "Passive",
        "passive_cfg": {"power": -800, "cd_time": 600},
    }


async def test_client_records_results_and_detects_silence() -> None:
    """Raw results are kept per method; a poll without any reply raises."""
    client = MarstekClient()
    with patch.object(
        MarstekUDPClient,
        "send_request",
        AsyncMock(return_value={"result": {"bat_cap": 1}}),
    ):
        await client.send_request(command_builder.get_es_status(), "h")
    assert client.results["h"]["ES.GetStatus"] == {"bat_cap": 1}

    with (
        patch.object(
            MarstekUDPClient,
            "get_device_status",
            AsyncMock(return_value=MarstekDeviceStatus(device_ip="h")),
        ),
        pytest.raises(TimeoutError),
    ):
        await client.get_device_status("h")
