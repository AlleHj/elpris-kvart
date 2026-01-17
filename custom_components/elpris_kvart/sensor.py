# Version: 2025-12-19-rev18
"""Sensor platform for Elpris Kvart."""
import logging
from datetime import timedelta, datetime as DateTime

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_time

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)

from .const import (
    DOMAIN,
    INTEGRATION_NAME,
    MANUFACTURER,
    MODEL,
    CONF_PRICE_AREA,
    CONF_SURCHARGE_ORE,
    DEFAULT_PRICE_AREA,
    DEFAULT_SURCHARGE_ORE,
    ATTR_PRICE_AREA,
    ATTR_LAST_API_UPDATE,
    ATTR_RAW_TODAY,
    ATTR_TOMORROW_PRICES_ORE,
    ATTR_MIN_PRICE_TODAY_ORE,
    ATTR_MAX_PRICE_TODAY_ORE,
    ATTR_MIN_PRICE_TOMORROW_ORE,
    ATTR_MAX_PRICE_TOMORROW_ORE,
    ATTR_SPOT_PRICE_ORE_ON_SURCHARGE_SENSOR,
    ATTR_SURCHARGE_APPLIED_ORE_ON_SURCHARGE_SENSOR,
    ATTR_TOMORROW_PRICES_SEK,
    ATTR_MIN_PRICE_TODAY_SEK,
    ATTR_MAX_PRICE_TODAY_SEK,
    ATTR_MIN_PRICE_TOMORROW_SEK,
    ATTR_MAX_PRICE_TOMORROW_SEK,
    ATTR_SPOT_PRICE_SEK_ON_SURCHARGE_SENSOR,
    ATTR_SURCHARGE_APPLIED_SEK_ON_SURCHARGE_SENSOR,
    ICON_CURRENCY_SEK,
    ICON_SURCHARGE_DISPLAY,
)
from . import ElprisDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SEK_ROUNDING_DECIMALS = 4
ORE_ROUNDING_DECIMALS = 2

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Elpris Kvart sensor platform."""
    coordinator: ElprisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    price_area = entry.data.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

    sensors_to_add = [
        ElprisSpotSensorOre(coordinator, entry, price_area),
        ElprisInklusivePaslagSensorOre(coordinator, entry, price_area),
        ElprisSpotSensorSEK(coordinator, entry, price_area),
        ElprisInklusivePaslagSensorSEK(coordinator, entry, price_area),
        SurchargeOreSensor(entry, price_area),
        SurchargeSEKSensor(entry, price_area),
    ]
    async_add_entities(sensors_to_add)
    _LOGGER.debug(f"Added {len(sensors_to_add)} {INTEGRATION_NAME} sensor entities.")


class BaseElprisSensor(CoordinatorEntity[ElprisDataUpdateCoordinator], SensorEntity):
    """Base class for all Elpris Kvart sensors."""
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ElprisDataUpdateCoordinator,
        entry: ConfigEntry,
        price_area: str,
    ):
        super().__init__(coordinator)
        self._entry = entry
        self._price_area = price_area
        self._unsub_timer = None
        self._raw_current_spot_price_sek: float | None = None

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{INTEGRATION_NAME} ({price_area})",
            "manufacturer": MANUFACTURER,
            "model": f"{MODEL} ({price_area})",
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.debug(f"Sensor {self.entity_id} added to HASS.")
        self._update_internal_data(write_state=True)
        self._schedule_next_price_update()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_data_update_for_base)
        )
        if self.coordinator.last_update_success and self.coordinator.data:
             self._update_internal_data(write_state=True)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_data_update_for_base(self) -> None:
        if self.coordinator.last_update_success:
            self._update_internal_data(write_state=True)
        else:
            self._raw_current_spot_price_sek = None
            self._update_sensor_specific_data()
            if self.hass:
                self.async_write_ha_state()

    def _update_internal_data(self, write_state: bool = False) -> None:
        self._calculate_raw_current_spot_price_sek()
        self._update_sensor_specific_data()
        if write_state and self.hass:
            self.async_write_ha_state()

    def _calculate_raw_current_spot_price_sek(self) -> None:
        raw_price = None
        if self.coordinator.data:
            prices_for_today_list = self.coordinator.data.get(dt_util.now().date(), [])
            if prices_for_today_list:
                # Calculate current quarter start (00, 15, 30, 45)
                now = dt_util.now()
                quarter_minute = (now.minute // 15) * 15
                current_quarter_start_local = now.replace(minute=quarter_minute, second=0, microsecond=0)

                for price_info in prices_for_today_list:
                    try:
                        time_start_dt_local = dt_util.parse_datetime(price_info['time_start'])
                        # Compare strict equality including timezone info handled by dt_util
                        if time_start_dt_local == current_quarter_start_local:
                            raw_price = float(price_info['SEK_per_kWh'])
                            break
                    except (TypeError, ValueError, KeyError):
                        continue
        self._raw_current_spot_price_sek = raw_price

    def _update_sensor_specific_data(self) -> None:
        raise NotImplementedError()

    def _schedule_next_price_update(self) -> None:
        """Schedule update for the next 15-minute mark."""
        if self._unsub_timer:
            self._unsub_timer()

        now = dt_util.now()
        # Calculate the start of the current 15-minute period
        quarter_minute = (now.minute // 15) * 15
        current_quarter_start = now.replace(minute=quarter_minute, second=0, microsecond=0)

        # Next update is 15 minutes after the current period start
        next_update_time = current_quarter_start + timedelta(minutes=15)

        # Safety check: if calculation puts us in the past (milliseconds delay), add another 15 min
        if next_update_time <= now:
             next_update_time += timedelta(minutes=15)

        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_price_update_callback, next_update_time
        )

    async def _async_price_update_callback(self, now_triggered: DateTime) -> None:
        self._update_internal_data(write_state=True)
        self._schedule_next_price_update()

    def _format_raw_price_list_sek(self, raw_price_data_list: list) -> list:
        if not raw_price_data_list:
            return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                formatted_item = {"SEK_per_kWh": float(item["SEK_per_kWh"]), "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError):
                continue
        return formatted_prices

    def _format_raw_price_list_ore(self, raw_price_data_list: list) -> list:
        if not raw_price_data_list:
            return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                ore_price = round(float(item["SEK_per_kWh"]) * 100, ORE_ROUNDING_DECIMALS)
                formatted_item = {"ore_per_kWh": ore_price, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError):
                continue
        return formatted_prices

    def _format_raw_price_list_with_surcharge_ore(self, raw_price_data_list: list, surcharge_ore: float) -> list:
        if not raw_price_data_list:
            return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                spot_ore = float(item["SEK_per_kWh"]) * 100
                total_ore = round(spot_ore + surcharge_ore, ORE_ROUNDING_DECIMALS)
                formatted_item = {"ore_per_kWh": total_ore, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError):
                continue
        return formatted_prices

    def _format_raw_price_list_with_surcharge_sek(self, raw_price_data_list: list, surcharge_sek: float) -> list:
        if not raw_price_data_list:
            return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                spot_sek = float(item["SEK_per_kWh"])
                total_sek = round(spot_sek + surcharge_sek, SEK_ROUNDING_DECIMALS)
                formatted_item = {"SEK_per_kWh": total_sek, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError):
                continue
        return formatted_prices

    def _get_surcharge_ore_from_config(self) -> float:
        surcharge_val = self._entry.options.get(CONF_SURCHARGE_ORE, self._entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE))
        try:
            return float(surcharge_val)
        except (ValueError, TypeError):
            return DEFAULT_SURCHARGE_ORE

# --- Specific Sensor Implementations ---
class ElprisSpotSensorOre(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris i öre/kWh"
        object_id_part = f"elpris_kvart_{price_area.lower()}_ore_spot"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement = "öre/kWh"
        self._attr_suggested_display_precision = ORE_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY

    def _update_sensor_specific_data(self) -> None:
        if self._raw_current_spot_price_sek is not None:
            self._attr_native_value = round(self._raw_current_spot_price_sek * 100, ORE_ROUNDING_DECIMALS)
        else:
            self._attr_native_value = None

        attrs = {ATTR_PRICE_AREA: self._price_area}
        if self.coordinator.last_update_success and self.coordinator.last_api_call_timestamp:
            attrs[ATTR_LAST_API_UPDATE] = dt_util.as_local(self.coordinator.last_api_call_timestamp).isoformat()
        if self.coordinator.data:
            today_prices_raw = self.coordinator.data.get(dt_util.now().date(), [])
            attrs[ATTR_RAW_TODAY] = self._format_raw_price_list_ore(today_prices_raw)
            if attrs[ATTR_RAW_TODAY]:
                ore_values = [p['ore_per_kWh'] for p in attrs[ATTR_RAW_TODAY] if 'ore_per_kWh' in p]
                if ore_values:
                    attrs[ATTR_MIN_PRICE_TODAY_ORE] = min(ore_values)
                    attrs[ATTR_MAX_PRICE_TODAY_ORE] = max(ore_values)

            tomorrow_prices_raw = self.coordinator.data.get(dt_util.now().date() + timedelta(days=1), [])
            attrs[ATTR_TOMORROW_PRICES_ORE] = self._format_raw_price_list_ore(tomorrow_prices_raw)
            if attrs[ATTR_TOMORROW_PRICES_ORE]:
                ore_values = [p['ore_per_kWh'] for p in attrs[ATTR_TOMORROW_PRICES_ORE] if 'ore_per_kWh' in p]
                if ore_values:
                    attrs[ATTR_MIN_PRICE_TOMORROW_ORE] = min(ore_values)
                    attrs[ATTR_MAX_PRICE_TOMORROW_ORE] = max(ore_values)
        self._attr_extra_state_attributes = attrs

class ElprisInklusivePaslagSensorOre(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris + påslag i öre/kWh"
        object_id_part = f"elpris_kvart_{price_area.lower()}_ore_total"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement = "öre/kWh"
        self._attr_suggested_display_precision = ORE_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY

    def _update_sensor_specific_data(self) -> None:
        surcharge_ore = self._get_surcharge_ore_from_config()
        spot_ore_calculated = None
        if self._raw_current_spot_price_sek is not None:
            spot_ore_calculated = round(self._raw_current_spot_price_sek * 100, ORE_ROUNDING_DECIMALS)
            self._attr_native_value = round(spot_ore_calculated + surcharge_ore, ORE_ROUNDING_DECIMALS)
        else:
            self._attr_native_value = None

        attrs = {
            ATTR_PRICE_AREA: self._price_area,
            ATTR_SPOT_PRICE_ORE_ON_SURCHARGE_SENSOR: spot_ore_calculated,
            ATTR_SURCHARGE_APPLIED_ORE_ON_SURCHARGE_SENSOR: surcharge_ore,
        }
        if self.coordinator.last_update_success and self.coordinator.last_api_call_timestamp:
            attrs[ATTR_LAST_API_UPDATE] = dt_util.as_local(self.coordinator.last_api_call_timestamp).isoformat()

        if self.coordinator.data:
            today_prices_raw = self.coordinator.data.get(dt_util.now().date(), [])
            attrs[ATTR_RAW_TODAY] = self._format_raw_price_list_with_surcharge_ore(today_prices_raw, surcharge_ore)

        self._attr_extra_state_attributes = attrs

class ElprisSpotSensorSEK(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris i SEK/kWh"
        object_id_part = f"elpris_kvart_{price_area.lower()}_sek_spot"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement = "SEK/kWh"
        self._attr_suggested_display_precision = SEK_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY

    def _update_sensor_specific_data(self) -> None:
        if self._raw_current_spot_price_sek is not None:
            self._attr_native_value = round(self._raw_current_spot_price_sek, SEK_ROUNDING_DECIMALS)
        else:
            self._attr_native_value = None

        attrs = {ATTR_PRICE_AREA: self._price_area}
        if self.coordinator.last_update_success and self.coordinator.last_api_call_timestamp:
            attrs[ATTR_LAST_API_UPDATE] = dt_util.as_local(self.coordinator.last_api_call_timestamp).isoformat()
        if self.coordinator.data:
            today_prices_raw = self.coordinator.data.get(dt_util.now().date(), [])
            attrs[ATTR_RAW_TODAY] = self._format_raw_price_list_sek(today_prices_raw)
            if attrs[ATTR_RAW_TODAY]:
                sek_values = [p['SEK_per_kWh'] for p in attrs[ATTR_RAW_TODAY] if 'SEK_per_kWh' in p]
                if sek_values:
                    attrs[ATTR_MIN_PRICE_TODAY_SEK] = min(sek_values)
                    attrs[ATTR_MAX_PRICE_TODAY_SEK] = max(sek_values)

            tomorrow_prices_raw = self.coordinator.data.get(dt_util.now().date() + timedelta(days=1), [])
            attrs[ATTR_TOMORROW_PRICES_SEK] = self._format_raw_price_list_sek(tomorrow_prices_raw)
            if attrs[ATTR_TOMORROW_PRICES_SEK]:
                sek_values = [p['SEK_per_kWh'] for p in attrs[ATTR_TOMORROW_PRICES_SEK] if 'SEK_per_kWh' in p]
                if sek_values:
                    attrs[ATTR_MIN_PRICE_TOMORROW_SEK] = min(sek_values)
                    attrs[ATTR_MAX_PRICE_TOMORROW_SEK] = max(sek_values)
        self._attr_extra_state_attributes = attrs

class ElprisInklusivePaslagSensorSEK(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris + påslag i SEK/kWh"
        object_id_part = f"elpris_kvart_{price_area.lower()}_sek_total"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement = "SEK/kWh"
        self._attr_suggested_display_precision = SEK_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY

    def _get_surcharge_sek_from_config(self) -> float:
        return round(self._get_surcharge_ore_from_config() / 100.0, SEK_ROUNDING_DECIMALS)

    def _update_sensor_specific_data(self) -> None:
        surcharge_sek = self._get_surcharge_sek_from_config()
        spot_sek_calculated = None
        if self._raw_current_spot_price_sek is not None:
            spot_sek_calculated = round(self._raw_current_spot_price_sek, SEK_ROUNDING_DECIMALS)
            self._attr_native_value = round(spot_sek_calculated + surcharge_sek, SEK_ROUNDING_DECIMALS)
        else:
            self._attr_native_value = None

        attrs = {
            ATTR_PRICE_AREA: self._price_area,
            ATTR_SPOT_PRICE_SEK_ON_SURCHARGE_SENSOR: spot_sek_calculated,
            ATTR_SURCHARGE_APPLIED_SEK_ON_SURCHARGE_SENSOR: surcharge_sek,
        }
        if self.coordinator.last_update_success and self.coordinator.last_api_call_timestamp:
            attrs[ATTR_LAST_API_UPDATE] = dt_util.as_local(self.coordinator.last_api_call_timestamp).isoformat()

        if self.coordinator.data:
            today_prices_raw = self.coordinator.data.get(dt_util.now().date(), [])
            attrs[ATTR_RAW_TODAY] = self._format_raw_price_list_with_surcharge_sek(today_prices_raw, surcharge_sek)

        self._attr_extra_state_attributes = attrs

# --- New Surcharge Display Sensors ---
class SurchargeDisplaySensorBase(SensorEntity):
    """Base class for surcharge display sensors."""
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = ICON_SURCHARGE_DISPLAY
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._entry = entry
        self._price_area = price_area
        self._update_surcharge_value()

        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"{INTEGRATION_NAME} ({price_area})",
            "manufacturer": MANUFACTURER,
            "model": f"{MODEL} ({price_area})",
            "entry_type": DeviceEntryType.SERVICE,
        }

    def _get_surcharge_ore_from_config(self) -> float:
        """Helper to get surcharge in öre from config entry."""
        return float(self._entry.options.get(
            CONF_SURCHARGE_ORE,
            self._entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE)
        ))

    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value based on the config. Must be implemented by subclasses."""
        raise NotImplementedError()


class SurchargeOreSensor(SurchargeDisplaySensorBase):
    """Sensor to display the configured surcharge in öre/kWh."""

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._attr_name = "Spotpris påslag Öre/kWh"
        self._attr_unique_id = f"{entry.entry_id}_elpris_paslag_ore_{price_area.lower()}"
        self._attr_native_unit_of_measurement = "öre/kWh"
        self._attr_suggested_display_precision = ORE_ROUNDING_DECIMALS
        super().__init__(entry, price_area)

    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value to the surcharge in öre."""
        self._attr_native_value = round(self._get_surcharge_ore_from_config(), ORE_ROUNDING_DECIMALS)


class SurchargeSEKSensor(SurchargeDisplaySensorBase):
    """Sensor to display the configured surcharge in SEK/kWh."""

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._attr_name = "Spotpris påslag SEK/kWh"
        self._attr_unique_id = f"{entry.entry_id}_elpris_paslag_sek_{price_area.lower()}"
        self._attr_native_unit_of_measurement = "SEK/kWh"
        self._attr_suggested_display_precision = SEK_ROUNDING_DECIMALS
        super().__init__(entry, price_area)

    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value to the surcharge in SEK."""
        surcharge_ore = self._get_surcharge_ore_from_config()
        self._attr_native_value = round(surcharge_ore / 100.0, SEK_ROUNDING_DECIMALS)