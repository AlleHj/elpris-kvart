# Version: 2025-05-21-rev13
"""The Elpris Timme integration."""
import asyncio
import logging
from datetime import timedelta, date as DateObject, datetime as DateTimeObject

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLATFORMS,
    API_BASE_URL,
    DEFAULT_PRICE_AREA,
    CONF_PRICE_AREA,
    DAILY_FETCH_HOUR,
    RETRY_INTERVAL_MINUTES,
    NORMAL_UPDATE_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elpris Timme from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    price_area = entry.data.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

    coordinator = ElprisDataUpdateCoordinator(hass, price_area, entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    entry.async_on_unload(entry.add_update_listener(options_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug(f"Configuration options for {entry.title} have been updated, reloading integration.")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
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
        api_url = f"{API_BASE_URL}/{year}/{month_day_str}_{self._price_area}.json"
        _LOGGER.debug(f"Requesting prices from: {api_url}")

        try:
            async with self._session.get(api_url, timeout=20) as response:
                if response.status == 404:
                    _LOGGER.info(
                        f"Prices not found (404) for {target_date} in area {self._price_area}."
                    )
                    return None
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug(
                    f"Successfully fetched {len(data)} price points for {target_date}"
                )
                return data
        except asyncio.TimeoutError:
            _LOGGER.warning(
                f"Timeout when fetching prices for {target_date} from {api_url}"
            )
        except Exception as e:
            _LOGGER.error(
                f"Error fetching prices for {target_date} from {api_url}: {e}"
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

    def _parse_and_validate_prices(self, raw_prices_list: list, expected_date: DateObject) -> list:
        """Parses raw price data, validates, and ensures SEK_per_kWh is float."""
        parsed_prices = []
        if not isinstance(raw_prices_list, list):
            _LOGGER.warning(
                f"Expected a list of prices for {expected_date}, got {type(raw_prices_list)}. Raw: {raw_prices_list}"
            )
            return []

        for item in raw_prices_list:
            try:
                price_value_sek = float(item["SEK_per_kWh"]) 
                time_start_str = item["time_start"]
                time_end_str = item.get("time_end") 
                
                time_start_dt = dt_util.parse_datetime(time_start_str)
                if time_start_dt is None:
                    raise ValueError(f"Failed to parse time_start: {time_start_str}")

                if time_start_dt.astimezone(dt_util.get_default_time_zone()).date() != expected_date:
                    _LOGGER.warning(
                        f"Price entry for date {time_start_dt.date()} "
                        f"found in data requested for {expected_date}. Skipping. Entry: {item}"
                    )
                    continue
                
                entry_to_add = {
                    "time_start": time_start_str,
                    "SEK_per_kWh": price_value_sek, 
                }
                if time_end_str: 
                    entry_to_add["time_end"] = time_end_str
                parsed_prices.append(entry_to_add)

            except (KeyError, ValueError, TypeError) as e:
                _LOGGER.warning(
                    f"Skipping invalid price entry for {expected_date}: {item}. Error: {e}"
                )
                continue
        
        parsed_prices.sort(key=lambda p: dt_util.parse_datetime(p["time_start"]))
        return parsed_prices

    async def _async_update_data(self) -> dict[DateObject, list]:
        """Fetch data from API and update internal state."""
        _LOGGER.debug(f"Coordinator update triggered for price area {self.price_area}")
        
        now_local = dt_util.now()
        today_local_date = now_local.date()
        tomorrow_local_date = today_local_date + timedelta(days=1)
        
        if today_local_date not in self.all_prices or not self.all_prices[today_local_date]:
            _LOGGER.info(f"Fetching prices for today: {today_local_date}")
            prices_today_raw = await self.api.get_prices(today_local_date)
            if prices_today_raw:
                self.all_prices[today_local_date] = self._parse_and_validate_prices(prices_today_raw, today_local_date)
            else:
                _LOGGER.warning(f"Could not fetch prices for today {today_local_date}.")

        time_to_fetch_tomorrow = now_local.hour >= DAILY_FETCH_HOUR
        tomorrow_prices_needed = self.tomorrow_prices_successfully_fetched_for_date != tomorrow_local_date

        if time_to_fetch_tomorrow and tomorrow_prices_needed:
            _LOGGER.info(
                f"Attempting to fetch prices for tomorrow: {tomorrow_local_date} "
                f"(current time: {now_local.strftime('%H:%M')})"
            )
            prices_tomorrow_raw = await self.api.get_prices(tomorrow_local_date)
            if prices_tomorrow_raw:
                self.all_prices[tomorrow_local_date] = self._parse_and_validate_prices(prices_tomorrow_raw, tomorrow_local_date)
                self.tomorrow_prices_successfully_fetched_for_date = tomorrow_local_date
                _LOGGER.info(
                    f"Successfully fetched {len(self.all_prices[tomorrow_local_date])} "
                    f"prices for tomorrow {tomorrow_local_date}"
                )
                if self.update_interval != timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS):
                    _LOGGER.debug("Tomorrow's prices fetched, setting update interval to normal.")
                    self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)
            else:
                _LOGGER.warning(
                    f"Failed to fetch prices for tomorrow {tomorrow_local_date}. Will retry."
                )
                if self.update_interval != timedelta(minutes=RETRY_INTERVAL_MINUTES):
                    _LOGGER.debug(
                        f"Fetch for tomorrow failed, setting update interval to {RETRY_INTERVAL_MINUTES} minutes for retries."
                    )
                    self.update_interval = timedelta(minutes=RETRY_INTERVAL_MINUTES)
        elif not time_to_fetch_tomorrow and self.tomorrow_prices_successfully_fetched_for_date == tomorrow_local_date:
            if self.update_interval != timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS):
                _LOGGER.debug("Ensuring update interval is normal as tomorrow's prices are available.")
                self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)

        if now_local.hour < DAILY_FETCH_HOUR and self.tomorrow_prices_successfully_fetched_for_date == today_local_date:
            _LOGGER.info(
                f"It's a new day (before {DAILY_FETCH_HOUR}:00), "
                f"resetting 'tomorrow_prices_successfully_fetched_for_date' status."
            )
            self.tomorrow_prices_successfully_fetched_for_date = None
            if self.update_interval != timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS):
                 self.update_interval = timedelta(hours=NORMAL_UPDATE_INTERVAL_HOURS)
        
        day_before_yesterday = today_local_date - timedelta(days=2)
        keys_to_delete = [
            date_key for date_key in self.all_prices if date_key < day_before_yesterday
        ]
        if keys_to_delete:
            _LOGGER.debug(f"Cleaning up old price data for dates: {keys_to_delete}")
            for key_to_delete in keys_to_delete:
                if key_to_delete in self.all_prices:
                    del self.all_prices[key_to_delete]
        
        if not self.all_prices.get(today_local_date):
            _LOGGER.warning(
                f"No price data available for today ({today_local_date}) after update attempt."
            )

        _LOGGER.debug(
            f"Coordinator update finished. Current all_prices keys: {list(self.all_prices.keys())}. "
            f"Tomorrow's prices fetched for: {self.tomorrow_prices_successfully_fetched_for_date}. "
            f"Next update interval: {self.update_interval}."
        )
        
        self.last_api_call_timestamp = dt_util.utcnow() 
        return self.all_prices