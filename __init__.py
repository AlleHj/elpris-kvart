# Version: 2025-05-28-v0.1.4
"""The Elpris Timme integration."""

import asyncio
import logging
from datetime import date as DateObject  # Ruff I001: Sorted imports
from datetime import datetime as DateTimeObject  # Ruff I001: Sorted imports
from datetime import timedelta  # Ruff I001: Sorted imports

import aiohttp  # För att kunna fånga aiohttp.ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (  # Ruff I001: Sorted imports
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

    def __init__(self, session: aiohttp.ClientSession, price_area: str):
        """Initialize the API communication."""
        self._session = session
        self._price_area = price_area

    async def get_prices(self, target_date: DateObject) -> list | None:
        """Fetch prices for a specific date and price area."""
        year = target_date.year
        month_day_str = target_date.strftime("%m-%d")
        api_url = f"{API_BASE_URL}/{year}/{month_day_str}_{self._price_area}.json"
        _LOGGER.debug("Requesting prices from: %s", api_url)

        try:
            async with self._session.get(api_url, timeout=20) as response:
                if response.status == 404:
                    _LOGGER.info(
                        "Prices not found (404) for %s in area %s.",
                        target_date,
                        self._price_area,
                    )
                    return None
                response.raise_for_status()  # Kan generera aiohttp.ClientResponseError
                data = (
                    await response.json()
                )  # Kan generera ContentTypeError/JSONDecodeError
                _LOGGER.debug(
                    "Successfully fetched %d price points for %s",
                    len(data),
                    target_date,
                )
                return data
        except TimeoutError:  # Ruff UP041: Byt asyncio.TimeoutError till TimeoutError
            _LOGGER.warning(
                "Timeout when fetching prices for %s from %s", target_date, api_url
            )
        except (
            aiohttp.ClientError
        ) as e:  # Ruff BLE001 / Pylint W0718: Fånga mer specifik error
            _LOGGER.error(
                "aiohttp.ClientError fetching prices for %s from %s: %s",
                target_date,
                api_url,
                e,
            )
        # Fortfarande en bredare fallback, men logga att det var oväntat.
        except (
            Exception
        ) as e:  # Pylint W0718 / Ruff BLE001 (Fortfarande bred, men sista utväg)
            _LOGGER.error(
                "Unexpected Exception fetching prices for %s from %s: %s (%s)",
                target_date,
                api_url,
                e,
                type(e).__name__,  # Logga typen av exception för felsökning
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
            name=f"{DOMAIN} ({self.price_area})",
            update_method=self._async_update_data,
            update_interval=self._current_update_interval,
        )
        _LOGGER.debug(
            "ElprisDataUpdateCoordinator initialized for %s. Debug mode: %s",
            self.price_area,
            self._entry.options.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE),
        )

    def _validate_price_item_time_start(
        self, time_start_str: str, expected_date: DateObject
    ) -> DateTimeObject:
        """Validate and parse time_start, raise ValueError if invalid for TRY301."""
        # Denna funktion hjälper till med TRY301 genom att isolera raise.
        # Dock kommer ValueError fortfarande fångas av den yttre loopen.
        # För att helt undvika TRY301 här, skulle felet behöva hanteras annorlunda,
        # men det skulle ändra logiken för att skippa felaktiga items.
        # Vi lämnar den som den är för nu, då beteendet är avsiktligt.
        dt_val = dt_util.parse_datetime(time_start_str)
        if dt_val is None:
            # Detta kommer fortfarande att flaggas av TRY301 om det inte är i en egen funktion
            # som anropas *utanför* try-blocket som fångar ValueError.
            # Vi accepterar denna varning för nu, då logiken är att fånga och fortsätta.
            raise ValueError(f"Failed to parse time_start: {time_start_str}")
        if dt_val.astimezone(dt_util.get_default_time_zone()).date() != expected_date:
            _LOGGER.warning(
                "Price entry for date %s found in data requested for %s. Skipping.",
                dt_val.date(),
                expected_date,
            )
            # Signalera att denna ska skippas, men inte nödvändigtvis ett "fel" för hela listan
            raise ValueError(f"Mismatched date for item: {time_start_str}")
        return dt_val

    def _parse_and_validate_prices(
        self, raw_prices_list: list, expected_date: DateObject
    ) -> list:
        """Parse raw price data, validate, and ensure SEK_per_kWh is float."""  # Ruff D401: Ändrat "Parses" till "Parse"
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
                time_end_str = item.get("time_end")  # Kan vara None

                # Försök att följa TRY301 genom att validera utanför huvud-try för just detta.
                # Men i detta fall är det avsiktligt att ValueError fångas för att skippa item.
                # time_start_dt = self._validate_price_item_time_start(time_start_str, expected_date)
                # Ovanstående _validate_price_item_time_start kommer fortfarande flaggas av TRY301
                # om den raisar ValueError och anropas inom denna try-except.
                # Vi behåller den enklare strukturen och noterar TRY301.

                time_start_dt = dt_util.parse_datetime(time_start_str)
                if time_start_dt is None:
                    # Denna raise kommer att fångas av except nedan, vilket är avsiktligt.
                    # Ruff TRY301 varnar för detta mönster.
                    raise ValueError(f"Failed to parse time_start from item: {item}")

                if (
                    time_start_dt.astimezone(dt_util.get_default_time_zone()).date()
                    != expected_date
                ):
                    _LOGGER.warning(
                        "Price entry for date %s found in data requested for %s. "
                        "Skipping. Entry: %s",
                        time_start_dt.date(),
                        expected_date,
                        item,
                    )
                    continue  # Hoppa över detta item

                entry_to_add = {
                    "time_start": time_start_str,
                    "SEK_per_kWh": price_value_sek,
                }
                if time_end_str:  # Lägg bara till time_end om det finns
                    entry_to_add["time_end"] = time_end_str
                parsed_prices.append(entry_to_add)

            except (KeyError, ValueError, TypeError) as e:
                _LOGGER.warning(
                    "Skipping invalid price entry for %s: %s. Error: %s (%s)",
                    expected_date,
                    item,
                    e,
                    type(e).__name__,
                )
                continue  # Hoppa över detta item

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
                "No prices for today (%s) in cache or cache is empty, "
                "attempting fetch.",
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
                "Attempting to fetch prices for tomorrow: %s (current time: %s, "
                "fetch hour: %s)",
                tomorrow_local_date,
                now_local.strftime("%H:%M"),
                DAILY_FETCH_HOUR,
            )
            prices_tomorrow_raw = await self.api.get_prices(tomorrow_local_date)
            if prices_tomorrow_raw:
                validated_prices = self._parse_and_validate_prices(
                    prices_tomorrow_raw, tomorrow_local_date
                )
                self.all_prices[tomorrow_local_date] = validated_prices
                self.tomorrow_prices_successfully_fetched_for_date = tomorrow_local_date
                _LOGGER.info(
                    "Successfully fetched %d prices for tomorrow %s",
                    len(validated_prices),
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
                        "Fetch for tomorrow failed, setting update interval to %d "
                        "minutes for retries.",
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
                    "Ensuring update interval is normal as tomorrow's prices are "
                    "available and it's before fetch hour."
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
                "It's a new day (before %s:00), resetting "
                "'tomorrow_prices_successfully_fetched_for_date' status (was %s).",
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
                if key_to_delete in self.all_prices:  # Säkerställ att nyckeln finns
                    del self.all_prices[key_to_delete]

        if not self.all_prices.get(today_local_date):
            _LOGGER.warning(
                "No price data available for today (%s) after update attempt.",
                today_local_date,
            )

        _LOGGER.debug(
            "Coordinator update finished. All_prices keys: %s. Tomorrow fetched for: %s. "
            "Next update: %s.",
            list(self.all_prices.keys()),
            self.tomorrow_prices_successfully_fetched_for_date,
            self.update_interval,
        )

        self.last_api_call_timestamp = dt_util.utcnow()
        return self.all_prices
