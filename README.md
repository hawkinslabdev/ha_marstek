# Marstek for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Install_this_repository-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hawkinslabdev&repository=ha_marstek&category=integration)
[![Tests](https://img.shields.io/github/actions/workflow/status/hawkinslabdev/ha_marstek/tests.yml?branch=main&label=tests)](https://github.com/hawkinslabdev/ha_marstek/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-non--commercial-orange.svg)](LICENSE.md)

This fork of the Marstek integration is now an un-official Home Assistant integration first set-up Marstek, but extended with a personal vision on how this should be integrated. 

This Marstek Battery integration communicates with supported Marstek energy storage devices locally over UDP and exposes their status as Home Assistant sensors.

## Installation

Installation runs through [HACS](https://hacs.xyz) as a custom repository. The button below adds the repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hawkinslabdev&repository=ha_marstek&category=integration)

1. Select the button above, or open **HACS** > **⋮** > **Custom repositories** and add `https://github.com/hawkinslabdev/ha_marstek` with type **Integration**.
2. Download **Marstek (unofficial)** and restart Home Assistant.
3. [Add the Marstek integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=marstek) or open **Settings** > **Devices & services** > **Add integration** > **Marstek (unofficial)**.
4. Select a setup method:
   - **Search for devices on the local network**: UDP broadcast discovery.
   - **Enter device IP address**: manual setup.

Setup requires the device to be powered on, reachable from Home Assistant, and running with Open API enabled.

## Requirements

- Home Assistant Core 2026+
- Home Assistant and the Marstek device must be on the same local network.
- Open API must be enabled on the Marstek device.

## Supported Devices

The integration currently supports these device types. A device may report either its model name or one of the protocol identifiers below:

| Device | Supported | Reported device type |
| --- | --- | --- |
| Venus A | Yes | `VNSA-0`, `VenusA`, `Venus A` |
| Venus D | Yes | `VNSD-0`, `VenusD`, `Venus D` |
| Venus E 1.0 | No | — |
| Venus E 2.0 | No | — |
| Venus E 3.0 | Yes | `VNSE3-0`, `VenusE 3.0`, `Venus E 3.0` |

Support depends on the device firmware exposing the Marstek Open API. Other device types are rejected during setup until they are explicitly supported.

## Available Entities

<details>
<summary>Sensors, controls, and data sources</summary>

<br>

| Entity | Type | Source |
| --- | --- | --- |
| State of charge | Sensor (%) | `ES.GetStatus` / `ES.GetMode` `bat_soc`; unknown while `bat_cap` is `0` |
| Battery power, battery status | Sensor (W), enum (`charging`, `discharging`, `idle`) | `ongrid_power` magnitude and sign |
| Charging power, discharging power | Sensor (W) | `ongrid_power`, split by direction; `0` for the inactive direction |
| Battery energy in, battery energy out | Sensor (kWh, total increasing) | `ES.GetStatus` `total_grid_input_energy`, `total_grid_output_energy` (AC side) |
| Stored energy | Sensor (kWh) | `bat_cap` × `bat_soc`; unknown while `bat_cap` is `0` |
| Device mode | Sensor (enum) | `ES.GetMode` `mode` |
| PV1–PV4 power, voltage, current, state; lifetime PV energy | Sensor | `PV.GetStatus`, `total_pv_energy`; created for Venus A/D only |
| Operating mode | Select (`Auto`, `AI`, `Passive`, `UPS`) | `ES.SetMode`; `Manual` requires an app schedule and reports as unknown |
| Passive power | Number (W, −2500 to 2500) | `passive_cfg.power`; negative charges, positive discharges |
| Passive duration | Number (s, 60 to 86400) | `passive_cfg.cd_time` |

Passive power and duration are stored in Home Assistant and restored after restart. Changes apply immediately while the device is in passive mode, otherwise on the next switch to `Passive`.

Battery energy in and out map to the **Battery storage** section of the Energy dashboard.

Some firmware (Venus E 3.0 v148) reports `0` for `bat_soc`, `bat_cap`, and every `Bat.GetStatus` field. State of charge and stored energy stay unknown on that firmware.

</details>

<details>
<summary>Data quality</summary>

<br>

Readings that drop to implausible values are replaced with the previous value: energy counters that decrease, `bat_cap` of `0`, and a battery level of `0` % after a reading of 10 % or more.

</details>

<details>
<summary>Repairs and diagnostics</summary>

<br>

A repair issue is raised after 10 consecutive polls (5 minutes) without an Open API response, a common result of firmware updates resetting Open API. The issue clears on the next successful poll. Entities report `unavailable` while the device is silent.

**Download diagnostics** on the device page exports device information, normalized status, and the raw results of the last poll. MAC addresses, Wi-Fi name, and `src` identifiers are redacted.

</details>

The device is polled locally every 30 seconds. No cloud account or external service is required.

# License

This is a fork of [MarstekEnergy/ha_marstek](https://github.com/MarstekEnergy/ha_marstek), thus inheriting its proprietery license.
