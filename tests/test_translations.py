"""Tests for Marstek translations."""

import json
from pathlib import Path

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.marstek_hacs.const import DOMAIN

TRANSLATIONS = Path(__file__).parents[1] / "custom_components" / DOMAIN / "translations"


def _keys(data: dict, prefix: str = "") -> set[str]:
    return {
        key
        for name, value in data.items()
        for key in (
            _keys(value, f"{prefix}{name}.")
            if isinstance(value, dict)
            else {f"{prefix}{name}"}
        )
    }


@pytest.mark.parametrize("language", ["de", "fr", "nl"])
def test_translation_keys_match_english(language: str) -> None:
    """Every language file has exactly the keys of en.json."""
    english = json.loads((TRANSLATIONS / "en.json").read_text())
    other = json.loads((TRANSLATIONS / f"{language}.json").read_text())
    assert _keys(other) == _keys(english)


@pytest.mark.usefixtures("init_integration")
async def test_dutch_entity_name(hass: HomeAssistant) -> None:
    """Home Assistant loads the Dutch entity names."""
    translations = await async_get_translations(hass, "nl", "entity", {DOMAIN})
    assert (
        translations[f"component.{DOMAIN}.entity.sensor.battery_soc.name"]
        == "Laadpercentage"
    )


@pytest.fixture
def dutch(hass: HomeAssistant) -> None:
    """Run Home Assistant in Dutch."""
    hass.config.language = "nl"


@pytest.mark.usefixtures("dutch", "init_integration")
async def test_entity_ids_english_on_dutch_instance(hass: HomeAssistant) -> None:
    """Entity IDs follow the English names whatever the instance language."""
    state = hass.states.get("sensor.marstek_venus_e_3_0_state_of_charge")
    assert state is not None
    assert state.attributes["friendly_name"] == "Marstek Venus E 3.0 Laadpercentage"
