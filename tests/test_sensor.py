"""Tester för Elpris Kvart sensorer."""
from unittest.mock import patch
from datetime import datetime, timedelta
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.elpris_kvart.const import DOMAIN, CONF_PRICE_AREA, CONF_SURCHARGE_ORE

# Mock-data i UTC (+00:00)
MOCK_PRICES_UTC = [
    {
        "SEK_per_kWh": 0.50,
        "time_start": "2023-10-25T00:00:00+00:00",
        "time_end": "2023-10-25T00:15:00+00:00",
    },
    {
        "SEK_per_kWh": 2.00,
        "time_start": "2023-10-25T12:00:00+00:00",
        "time_end": "2023-10-25T12:15:00+00:00",
    },
    {
        "SEK_per_kWh": 2.00,
        "time_start": "2023-10-25T12:15:00+00:00",
        "time_end": "2023-10-25T12:30:00+00:00",
    },
    {
        "SEK_per_kWh": 2.00,
        "time_start": "2023-10-25T12:30:00+00:00",
        "time_end": "2023-10-25T12:45:00+00:00",
    },
    {
        "SEK_per_kWh": 2.00,
        "time_start": "2023-10-25T12:45:00+00:00",
        "time_end": "2023-10-25T13:00:00+00:00",
    },
    {
        "SEK_per_kWh": 0.10,
        "time_start": "2023-10-25T13:00:00+00:00",
        "time_end": "2023-10-25T13:15:00+00:00",
    }
]

async def test_sensor_value_at_specific_time(hass: HomeAssistant, mock_elpris_api) -> None:
    """Testa att sensorn visar rätt pris vid en given tidpunkt (UTC)."""
    await hass.config.async_set_time_zone("UTC")
    mock_elpris_api.return_value = MOCK_PRICES_UTC

    mock_now = datetime(2023, 10, 25, 12, 15, 0, tzinfo=dt_util.UTC)

    with patch("homeassistant.util.dt.now", return_value=mock_now):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PRICE_AREA: "SE3", CONF_SURCHARGE_ORE: 10.0},
            options={CONF_SURCHARGE_ORE: 10.0}
        )
        config_entry.add_to_hass(hass)

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # 12:15 UTC -> 2.00 SEK (200 öre)
        # Entity ID: sensor.elpris_kvart_se3_spotpris_i_ore_kwh
        state_spot = hass.states.get("sensor.elpris_kvart_se3_spotpris_i_ore_kwh")
        assert state_spot is not None
        assert float(state_spot.state) == 200.0


async def test_sensor_update_on_time_change(hass: HomeAssistant, mock_elpris_api) -> None:
    """Testa att sensorn uppdaterar sig när priset ändras (UTC)."""
    await hass.config.async_set_time_zone("UTC")
    mock_elpris_api.return_value = MOCK_PRICES_UTC

    # Använd en lista för att hålla current_time "by reference" i lambdan
    time_container = [datetime(2023, 10, 25, 12, 59, 0, tzinfo=dt_util.UTC)]

    with patch("homeassistant.util.dt.now", side_effect=lambda: time_container[0]):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PRICE_AREA: "SE3", CONF_SURCHARGE_ORE: 0.0},
            options={CONF_SURCHARGE_ORE: 0.0}
        )
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # 12:59 UTC -> 200 öre
        state = hass.states.get("sensor.elpris_kvart_se3_spotpris_i_ore_kwh")
        assert state is not None
        assert float(state.state) == 200.0

        # Hoppa till 13:00:01 UTC
        new_time = time_container[0] + timedelta(minutes=1, seconds=1)
        time_container[0] = new_time

        from pytest_homeassistant_custom_component.common import async_fire_time_changed
        async_fire_time_changed(hass, new_time)
        await hass.async_block_till_done()

        # 13:00 UTC -> 10 öre
        state = hass.states.get("sensor.elpris_kvart_se3_spotpris_i_ore_kwh")
        assert state is not None
        assert float(state.state) == 10.0

async def test_sensor_attributes(hass: HomeAssistant, mock_elpris_api) -> None:
    """Testa attribut på sensorn (UTC)."""
    await hass.config.async_set_time_zone("UTC")
    mock_elpris_api.return_value = MOCK_PRICES_UTC

    mock_now = datetime(2023, 10, 25, 10, 0, 0, tzinfo=dt_util.UTC)

    with patch("homeassistant.util.dt.now", return_value=mock_now):
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        config_entry = MockConfigEntry(domain=DOMAIN, data={CONF_PRICE_AREA: "SE3"})
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.elpris_kvart_se3_spotpris_i_ore_kwh")
        assert state is not None
        attributes = state.attributes

        assert attributes["max_price_today_ore"] == 200.0
        assert attributes["min_price_today_ore"] == 10.0
        assert len(attributes["raw_today"]) == 6
