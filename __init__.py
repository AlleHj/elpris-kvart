# Version: 2025-05-28-v0.1.3
"""The Elpris Timme integration."""

import asyncio
import logging  # Behåll logging här
from datetime import timedelta, date as DateObject, datetime as DateTimeObject

# Standardbibliotek först, sedan tredjepart, sedan lokala. Alfabetiskt inom grupperna.
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (  # Dina lokala importer
    API_BASE_URL,
    CONF_DEBUG_MODE,
    CONF_PRICE_AREA,
    DAILY_FETCH_HOUR,
    DEFAULT_DEBUG_MODE,
    DEFAULT_PRICE_AREA,
    DOMAIN,
    NORMAL_UPDATE_INTERVAL_HOURS,
    PLATFORMS,
    RETRY_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


@callback
def _update_logger_level(entry: ConfigEntry) -> None:
    """Update the logger level based on the debug mode option."""
    debug_enabled = entry.options.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE)
    if debug_enabled:
        _LOGGER.setLevel(logging.DEBUG)
        _LOGGER.debug(
            "Debug logging has been enabled for Elpris Timme (%s).", entry.title
        )
    else:
        _LOGGER.setLevel(logging.INFO)
        _LOGGER.info(
            "Debug logging has been disabled for Elpris Timme (%s). Current level INFO.",
            entry.title,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elpris Timme from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _update_logger_level(entry)

    price_area = entry.data.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)
    coordinator = ElprisDataUpdateCoordinator(hass, price_area, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(options_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug(
        "Elpris Timme %s successfully set up with options: %s",
        entry.title,
        entry.options,
    )
    return True


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug(
        "Configuration options for %s have been updated: %s", entry.title, entry.options
    )
    _update_logger_level(entry)
    _LOGGER.debug("Reloading integration %s due to options update.", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Elpris Timme for %s", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Elpris Timme %s successfully unloaded.", entry.title)
    return unload_ok


class ElprisApi:
    """Simple class to communicate with the ElprisetJustNu API."""

    def __init__(self, session, price_area: str):
        """Initialize the API communication."""
        self._session = session
        self._price_area = price_area

    async def get_prices(self, target_date: DateObject) -> list | None:
        """Fetch prices for a specific date and price area."""
        year = target_date.year
        month_day_str = target_date.strftime("%m-%d")
        api_url = f"{API_BASE_URL}/{year}/{month_day_str}_{self._price_area}.json"  # f-string OK här, inte loggning
        _LOGGER.debug("Requesting prices from: %s", api_url)

        try:
            async with self._session.get(api_url, timeout=20) as response:
                if response.status == 404:
                    _LOGGER.info(  # Info-nivå, men kan också använda lazy
                        "Prices not found (404) for %s in area %s.",
                        target_date,
                        self._price_area,
                    )
                    return None
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug(
                    "Successfully fetched %d price points for %s",
                    len(data),
                    target_date,
                )
                return data
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timeout when fetching prices for %s from %s", target_date, api_url
            )
        except Exception as e:  # Behåll Exception as e
            _LOGGER.error(
                "Error fetching prices for %s from %s: %s", target_date, api_url, e
            )
        return None


class ElprisDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching and updating Elpris data."""

    def __init__(self, hass: HomeAssistant, price_area: str, entry: ConfigEntry):
        """Initialize the data update coordinator."""
        self.api = ElprisApi(async_get_clientsession(hass), price_area)
        self.price_area = price_area
        self._entry = entry

        self.all_prices: dict[DateObject, list] = {}
        self.tomorrow_prices_successfully_fetched_for_date: DateObject | None = None
        self.last_api_call_timestamp: DateTimeObject | None = None

        self._current_update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.price_area})",  # f-string OK här
            update_method=self._async_update_data,
            update_interval=self._current_update_interval,
        )
        _LOGGER.debug(
            "ElprisDataUpdateCoordinator initialized for %s. Debug mode: %s",
            self.price_area,
            self._entry.options.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE),
        )

    def _parse_and_validate_prices(
        self, raw_prices_list: list, expected_date: DateObject
    ) -> list:
        """Parses raw price data, validates, and ensures SEK_per_kWh is float."""
        parsed_prices = []
        if not isinstance(raw_prices_list, list):
            _LOGGER.warning(
                "Expected a list of prices for %s, got %s. Raw: %s",
                expected_date,
                type(raw_prices_list),
                raw_prices_list,
            )
            return []

        for item in raw_prices_list:
            try:
                price_value_sek = float(item["SEK_per_kWh"])
                time_start_str = item["time_start"]
                time_end_str = item.get("time_end")

                time_start_dt = dt_util.parse_datetime(time_start_str)
                if time_start_dt is None:
                    raise ValueError(
                        f"Failed to parse time_start: {time_start_str}"
                    )  # f-string OK i exception

                if (
                    time_start_dt.astimezone(dt_util.get_default_time_zone()).date()
                    != expected_date
                ):
                    _LOGGER.warning(
                        "Price entry for date %s found in data requested for %s. Skipping. Entry: %s",
                        time_start_dt.date(),
                        expected_date,
                        item,
                    )
                    continue

                entry_to_add = {
                    "time_start": time_start_str,
                    "SEK_per_kWh": price_value_sek,
                }
                if time_end_str:
                    entry_to_add["time_end"] = time_end_str
                parsed_prices.append(entry_to_add)

            except (KeyError, ValueError, TypeError) as e:  # Behåll Exception as e
                _LOGGER.warning(
                    "Skipping invalid price entry for %s: %s. Error: %s",
                    expected_date,
                    item,
                    e,
                )
                continue

        parsed_prices.sort(key=lambda p: dt_util.parse_datetime(p["time_start"]))
        _LOGGER.debug("Parsed %d prices for %s.", len(parsed_prices), expected_date)
        return parsed_prices

    async def _async_update_data(self) -> dict[DateObject, list]:
        """Fetch data from API and update internal state."""
        _LOGGER.debug("Coordinator update triggered for price area %s", self.price_area)

        now_local = dt_util.now()
        today_local_date = now_local.date()
        tomorrow_local_date = today_local_date + timedelta(days=1)

        if (
            today_local_date not in self.all_prices
            or not self.all_prices[today_local_date]
        ):
            _LOGGER.debug(
                "No prices for today (%s) in cache or cache is empty, attempting fetch.",
                today_local_date,
            )
            prices_today_raw = await self.api.get_prices(today_local_date)
            if prices_today_raw:
                self.all_prices[today_local_date] = self._parse_and_validate_prices(
                    prices_today_raw, today_local_date
                )
                _LOGGER.debug(
                    "Fetched %d prices for today %s.",
                    len(self.all_prices[today_local_date]),
                    today_local_date,
                )
            else:
                _LOGGER.warning(
                    "Could not fetch prices for today %s.", today_local_date
                )

        time_to_fetch_tomorrow = now_local.hour >= DAILY_FETCH_HOUR
        tomorrow_prices_needed = (
            self.tomorrow_prices_successfully_fetched_for_date != tomorrow_local_date
        )

        if time_to_fetch_tomorrow and tomorrow_prices_needed:
            _LOGGER.debug(
                "Attempting to fetch prices for tomorrow: %s (current time: %s, fetch hour: %s)",
                tomorrow_local_date,
                now_local.strftime("%H:%M"),
                DAILY_FETCH_HOUR,
            )
            prices_tomorrow_raw = await self.api.get_prices(tomorrow_local_date)
            if prices_tomorrow_raw:
                self.all_prices[tomorrow_local_date] = self._parse_and_validate_prices(
                    prices_tomorrow_raw, tomorrow_local_date
                )
                self.tomorrow_prices_successfully_fetched_for_date = tomorrow_local_date
                _LOGGER.info(  # Info
                    "Successfully fetched %d prices for tomorrow %s",
                    len(self.all_prices[tomorrow_local_date]),
                    tomorrow_local_date,
                )
                if self.update_interval != timedelta(
                    hours=NORMAL_UPDATE_INTERVAL_HOURS
                ):
                    _LOGGER.debug(
                        "Tomorrow's prices fetched, setting update interval to normal."
                    )
                    self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)
            else:
                _LOGGER.warning(
                    "Failed to fetch prices for tomorrow %s. Will retry.",
                    tomorrow_local_date,
                )
                if self.update_interval != timedelta(minutes=RETRY_INTERVAL_MINUTES):
                    _LOGGER.debug(
                        "Fetch for tomorrow failed, setting update interval to %d minutes for retries.",
                        RETRY_INTERVAL_MINUTES,
                    )
                    self.update_interval = timedelta(minutes=RETRY_INTERVAL_MINUTES)
        elif (
            not time_to_fetch_tomorrow
            and self.tomorrow_prices_successfully_fetched_for_date
            == tomorrow_local_date
        ):
            if self.update_interval != timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS):
                _LOGGER.debug(
                    "Ensuring update interval is normal as tomorrow's prices are available and it's before fetch hour."
                )
                self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)
        elif time_to_fetch_tomorrow and not tomorrow_prices_needed:
            _LOGGER.debug(
                "Tomorrow's prices for %s already fetched. No new fetch needed yet.",
                tomorrow_local_date,
            )

        if (
            now_local.hour < DAILY_FETCH_HOUR
            and self.tomorrow_prices_successfully_fetched_for_date == today_local_date
        ):
            _LOGGER.debug(
                "It's a new day (before %s:00), resetting 'tomorrow_prices_successfully_fetched_for_date' status (was %s).",
                DAILY_FETCH_HOUR,
                self.tomorrow_prices_successfully_fetched_for_date,
            )
            self.tomorrow_prices_successfully_fetched_for_date = None
            if self.update_interval != timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS):
                self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)

        day_before_yesterday = today_local_date - timedelta(days=2)
        keys_to_delete = [
            date_key for date_key in self.all_prices if date_key < day_before_yesterday
        ]
        if keys_to_delete:
            _LOGGER.debug("Cleaning up old price data for dates: %s", keys_to_delete)
            for key_to_delete in keys_to_delete:
                if key_to_delete in self.all_prices:
                    del self.all_prices[key_to_delete]

        if not self.all_prices.get(today_local_date):
            _LOGGER.warning(
                "No price data available for today (%s) after update attempt.",
                today_local_date,
            )

        _LOGGER.debug(
            "Coordinator update finished. Current all_prices keys: %s. Tomorrow's prices fetched for: %s. Next update interval: %s.",
            list(self.all_prices.keys()),
            self.tomorrow_prices_successfully_fetched_for_date,
            self.update_interval,
        )

        self.last_api_call_timestamp = dt_util.utcnow()
        return self.all_prices
