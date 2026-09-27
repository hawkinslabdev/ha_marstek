<p align="center">
  <img src="https://raw.githubusercontent.com/hawkinslabdev/ha_marstek/refs/heads/main/custom_components/marstek_hacs/brand/icon.png" alt="Logo" width="120" height="120">
</p>

<h1 align="center">Marstek for Home Assistant</h1>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=hawkinslabdev&repository=ha_marstek&category=integration"><img src="https://img.shields.io/badge/HACS-Install_this_repository-41BDF5?logo=homeassistantcommunitystore&logoColor=white" alt="HACS"></a>
  <a href="https://github.com/hawkinslabdev/ha_marstek/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/hawkinslabdev/ha_marstek/tests.yml?branch=main&label=tests" alt="Tests"></a>
  <a href="LICENSE.md"><img src="https://img.shields.io/badge/license-non--commercial-orange.svg" alt="License"></a>
</p>

Bring your Marstek batteries into Home Assistant through HACS. This unofficial integration is a fork of the original Marstek integration. It connects locally to supported Marstek energy storage devices over UDP using OpenAPI rather than Modbus TCP, and exposes their status as native Home Assistant sensors.

## Installation

Installation runs through [HACS](https://hacs.xyz) as a custom repository. The button below adds the repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=hawkinslabdev&repository=ha_marstek&category=integration)

1. Select the button above, or open **HACS** > **⋮** > **Custom repositories** and add `https://github.com/hawkinslabdev/ha_marstek` with type **Integration**.
2. Download **Marstek (unofficial)** and restart Home Assistant.
3. [Add the Marstek integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=marstek_hacs) or open **Settings** > **Devices & services** > **Add integration** > **Marstek (unofficial)**.
4. Select a setup method:
   - **Search for devices on the local network**: UDP broadcast discovery.
   - **Enter device IP address**: manual setup.

Setup requires the device to be powered on, reachable from Home Assistant, and running with Open API enabled.

The integration domain is `marstek_hacs` (folder `custom_components/marstek_hacs`) and runs alongside the official `marstek` integration. Installations from before the rename use the `marstek` domain: remove that config entry and the `custom_components/marstek` folder, then add the integration again. Entity IDs derive from the device name and are unchanged.

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

> [!TIP]
> With Marstek releasing new devices, we need your help testing and adding support for unreleased models. If you have an unsupported device, please open an issue or submit a pull request!

## Available Entities

<details>
<summary>Sensors, controls, and data sources</summary>

<br>

| Entity | Type | Source |
| --- | --- | --- |
| State of charge | Sensor (%) | `ES.GetStatus` / `ES.GetMode` `bat_soc` |
| Battery power, battery status | Sensor (W), enum (`charging`, `discharging`, `idle`) | `ongrid_power` magnitude and sign |
| Charging power, discharging power | Sensor (W) | `ongrid_power`, split by direction; `0` for the inactive direction |
| Battery energy in, battery energy out | Sensor (kWh, total increasing) | `ES.GetStatus` `total_grid_input_energy`, `total_grid_output_energy` (AC side) |
| Stored energy | Sensor (kWh) | `bat_cap` × `bat_soc` |
| Battery cycles | Sensor (diagnostic) | Equivalent full cycles: `total_grid_output_energy` ÷ `bat_cap`; AC-side energy, so slightly below the BMS count |
| Device mode | Sensor (enum) | `ES.GetMode` `mode` |
| PV1–PV4 power, voltage, current, state; lifetime PV energy | Sensor | `PV.GetStatus`, `total_pv_energy`; created for Venus A/D only |
| Operating mode | Select (`Auto`, `AI`, `Passive`, `UPS`) | `ES.SetMode`; `Manual` requires an app schedule and reports as unknown |
| Passive power | Number (W, −2500 to 2500) | `passive_cfg.power`; negative charges, positive discharges |
| Passive duration | Number (s, 60 to 86400) | `passive_cfg.cd_time` |
| Error state | Sensor (enum, diagnostic) | Outcome of the latest poll |

Passive power and duration are stored in Home Assistant and restored after restart. Changes apply immediately while the device is in passive mode, otherwise on the next switch to `Passive`.

</details>

<details>
<summary>Energy dashboard</summary>

<br>

Since integrations cannot directly register Energy dashboard sources and Home Assistant lacks a dedicated battery entity type, add the battery manually:

1. Navigate to **Settings** > **Dashboards** > **Energy**.
2. Select **Battery systems**.
3. Map the dialog fields:
* **Energy discharged from the battery:** `sensor.marstek_venus_e_3_0_battery_energy_out`
* **Energy charged into the battery:** `sensor.marstek_venus_e_3_0_battery_energy_in`
* **Power measurement type:** two sensors
* **Discharge power:** `sensor.marstek_venus_e_3_0_discharging_power`
* **Charge power:** `sensor.marstek_venus_e_3_0_charging_power`
* **State of charge sensor:** `sensor.marstek_venus_e_3_0_state_of_charge`
* **Usable capacity (kWh):** optional; only weights the combined state of charge across multiple batteries

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

The **Error state** diagnostic sensor reports the outcome of the latest poll (`none`, `no_response`, `network_error`, `invalid_data`) and stays available during outages. Log entries identify the device by `<ip>:<port>`; setup logs the model, reported device type, firmware version, and Open API revision (3.1).

**Download diagnostics** on the device page exports device information, normalized status, error state, Open API revision, and the latest raw reply per Open API request. MAC addresses, Wi-Fi name, and `src` identifiers are redacted.

The device is polled locally every 60 seconds. No cloud account or external service is required.

</details>

# License

This is a fork of [MarstekEnergy/ha_marstek](https://github.com/MarstekEnergy/ha_marstek), thus inheriting its proprietery license.
