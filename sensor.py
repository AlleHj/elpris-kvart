# Version: 2025-05-21-rev15
"""Sensor platform for Elpris Timme."""
import logging
from datetime import timedelta, datetime as DateTime

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_time

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)

from .const import (
    DOMAIN,
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
    ICON_SURCHARGE_DISPLAY, # Import new icon
)
from . import ElprisDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
SENSOR_VERSION = "2025-05-21-rev15"
_LOGGER.info(f"Elpris Timme Sensor Module Loaded - Version: {SENSOR_VERSION}")


SEK_ROUNDING_DECIMALS = 4 
ORE_ROUNDING_DECIMALS = 2 

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ElprisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    price_area = entry.data.get(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)

    sensors_to_add = [
        ElprisSpotSensorOre(coordinator, entry, price_area),
        ElprisInklusivePaslagSensorOre(coordinator, entry, price_area),
        ElprisSpotSensorSEK(coordinator, entry, price_area),
        ElprisInklusivePaslagSensorSEK(coordinator, entry, price_area),
        SurchargeOreSensor(entry, price_area), # New sensor
        SurchargeSEKSensor(entry, price_area), # New sensor
    ]
    async_add_entities(sensors_to_add)
    _LOGGER.debug(f"Added {len(sensors_to_add)} Elpris Timme sensor entities. Version: {SENSOR_VERSION}")


class BaseElprisSensor(CoordinatorEntity[ElprisDataUpdateCoordinator], SensorEntity):
    # ... (BaseElprisSensor class from rev14 is unchanged) ...
    _attr_should_poll = False 

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
            "name": f"Elpris Timme ({price_area})", 
            "manufacturer": "Custom ElprisTimme", 
            "model": f"API ({price_area})",
            "entry_type": "service", 
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass() 
        _LOGGER.info(f"Sensor {self.entity_id} (Name: {self.name}, Unique ID: {self.unique_id}) added to HASS.")
        self._update_internal_data(write_state=True) 
        self._schedule_next_hourly_price_update()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_data_update_for_base)
        )
        if self.coordinator.last_update_success and self.coordinator.data:
             _LOGGER.debug(f"Sensor {self.unique_id}: Coordinator has data on add, forcing update.")
             self._update_internal_data(write_state=True)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_timer: self._unsub_timer()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_data_update_for_base(self) -> None: 
        if self.coordinator.last_update_success:
            self._update_internal_data(write_state=True)
        else:
            self._raw_current_spot_price_sek = None 
            self._update_sensor_specific_data() 
            if self.hass: self.async_write_ha_state()

    def _update_internal_data(self, write_state: bool = False) -> None:
        self._calculate_raw_current_spot_price_sek()
        self._update_sensor_specific_data() 
        if write_state and self.hass: self.async_write_ha_state()

    def _calculate_raw_current_spot_price_sek(self) -> None:
        raw_price = None
        if self.coordinator.data:
            prices_for_today_list = self.coordinator.data.get(dt_util.now().date(), [])
            if prices_for_today_list:
                current_hour_start_local = dt_util.now().replace(minute=0, second=0, microsecond=0)
                for price_info in prices_for_today_list:
                    try:
                        time_start_dt_local = dt_util.parse_datetime(price_info['time_start'])
                        if time_start_dt_local == current_hour_start_local:
                            raw_price = float(price_info['SEK_per_kWh']) 
                            break
                    except (TypeError, ValueError, KeyError): continue 
        self._raw_current_spot_price_sek = raw_price
        _LOGGER.debug(f"Sensor {self.unique_id}: Calculated raw_spot_price_sek: {self._raw_current_spot_price_sek}")

    def _update_sensor_specific_data(self) -> None:
        raise NotImplementedError()

    def _schedule_next_hourly_price_update(self) -> None:
        if self._unsub_timer: self._unsub_timer()
        now = dt_util.now()
        current_hour_target_update = now.replace(minute=0, second=0, microsecond=0)
        next_update_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0) \
            if now >= current_hour_target_update else current_hour_target_update
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_hourly_price_update_callback, next_update_time
        )

    async def _async_hourly_price_update_callback(self, now_triggered: DateTime) -> None:
        self._update_internal_data(write_state=True) 
        self._schedule_next_hourly_price_update()

    def _format_raw_price_list_sek(self, raw_price_data_list: list) -> list:
        if not raw_price_data_list: return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                formatted_item = {"SEK_per_kWh": float(item["SEK_per_kWh"]), "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError): continue
        return formatted_prices

    def _format_raw_price_list_ore(self, raw_price_data_list: list) -> list:
        if not raw_price_data_list: return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                ore_price = round(float(item["SEK_per_kWh"]) * 100, ORE_ROUNDING_DECIMALS)
                formatted_item = {"ore_per_kWh": ore_price, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError): continue
        return formatted_prices
        
    def _format_raw_price_list_with_surcharge_ore(self, raw_price_data_list: list, surcharge_ore: float) -> list:
        if not raw_price_data_list: return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                spot_ore = float(item["SEK_per_kWh"]) * 100
                total_ore = round(spot_ore + surcharge_ore, ORE_ROUNDING_DECIMALS)
                formatted_item = {"ore_per_kWh": total_ore, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError): continue
        return formatted_prices

    def _format_raw_price_list_with_surcharge_sek(self, raw_price_data_list: list, surcharge_sek: float) -> list:
        if not raw_price_data_list: return []
        formatted_prices = []
        for item in raw_price_data_list:
            try:
                spot_sek = float(item["SEK_per_kWh"])
                total_sek = round(spot_sek + surcharge_sek, SEK_ROUNDING_DECIMALS)
                formatted_item = {"SEK_per_kWh": total_sek, "time_start": item["time_start"]}
                if "time_end" in item and item["time_end"] is not None:
                    formatted_item["time_end"] = item["time_end"]
                formatted_prices.append(formatted_item)
            except (KeyError, TypeError, ValueError): continue
        return formatted_prices

    def _get_surcharge_ore_from_config(self) -> float:
        surcharge_val = self._entry.options.get(CONF_SURCHARGE_ORE, self._entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE))
        try: return float(surcharge_val)
        except (ValueError, TypeError): return DEFAULT_SURCHARGE_ORE

# --- Specific Sensor Implementations ---
# Spot price sensors (unchanged from rev14, still using BaseElprisSensor)
class ElprisSpotSensorOre(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris i öre/kWh"
        object_id_part = f"timelpris_{price_area.lower()}_ore_spot"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"
        # self._attr_object_id = object_id_part # Uncomment if specific object_id needed

        self._attr_native_unit_of_measurement="öre/kWh"
        self._attr_suggested_display_precision=ORE_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY
        _LOGGER.debug(f"Initialized {self._attr_name} (Unique ID: {self.unique_id})")

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
        _LOGGER.info(f"{self.name} updated. Value: {self._attr_native_value}")

class ElprisInklusivePaslagSensorOre(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris + påslag i öre/kWh"
        object_id_part = f"timelpris_{price_area.lower()}_ore_total"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement="öre/kWh"
        self._attr_suggested_display_precision=ORE_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY
        _LOGGER.debug(f"Initialized {self._attr_name} (Unique ID: {self.unique_id})")

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
        _LOGGER.info(f"{self.name} updated. Value: {self._attr_native_value}")

class ElprisSpotSensorSEK(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris i SEK/kWh"
        object_id_part = f"timelpris_{price_area.lower()}_sek_spot"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement="SEK/kWh"
        self._attr_suggested_display_precision=SEK_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY
        _LOGGER.debug(f"Initialized {self._attr_name} (Unique ID: {self.unique_id})")

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
        _LOGGER.info(f"{self.name} updated. Value: {self._attr_native_value}")

class ElprisInklusivePaslagSensorSEK(BaseElprisSensor):
    def __init__(self, coordinator: ElprisDataUpdateCoordinator, entry: ConfigEntry, price_area: str):
        super().__init__(coordinator, entry, price_area)
        self._attr_name = "Spotpris + påslag i SEK/kWh"
        object_id_part = f"timelpris_{price_area.lower()}_sek_total"
        self._attr_unique_id = f"{entry.entry_id}_{object_id_part}"

        self._attr_native_unit_of_measurement="SEK/kWh"
        self._attr_suggested_display_precision=SEK_ROUNDING_DECIMALS
        self._attr_icon = ICON_CURRENCY_SEK
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.MONETARY
        _LOGGER.debug(f"Initialized {self._attr_name} (Unique ID: {self.unique_id})")

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
        _LOGGER.info(f"{self.name} updated. Value: {self._attr_native_value}")

# --- New Surcharge Display Sensors ---
class SurchargeDisplaySensorBase(SensorEntity):
    """Base class for surcharge display sensors."""
    _attr_should_poll = False # Value only changes on config change
    _attr_state_class = SensorStateClass.MEASUREMENT 
    _attr_device_class = SensorDeviceClass.MONETARY 
    _attr_icon = ICON_SURCHARGE_DISPLAY

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._entry = entry
        self._price_area = price_area # Used for unique_id and object_id grouping
        self._update_surcharge_value() # Set initial value

        # Device info to link to the same device as other Elpris Timme sensors
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Elpris Timme ({price_area})", # Matches device name of other sensors
            "manufacturer": "Custom ElprisTimme",
            "model": f"API ({price_area})",
            "entry_type": "service",
        }
        _LOGGER.debug(f"Initialized {self.name} (Unique ID: {self.unique_id}), Surcharge: {self._attr_native_value}")
        
    def _get_surcharge_ore_from_config(self) -> float:
        """Helper to get surcharge in öre from config entry."""
        # Options flow takes precedence if options have been set
        return float(self._entry.options.get(
            CONF_SURCHARGE_ORE, 
            self._entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE)
        ))

    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value based on the config. Must be implemented by subclasses."""
        raise NotImplementedError()

    # This method is not strictly needed if the integration reloads on option changes,
    # but good practice if we want to manually trigger updates in the future.
    # For now, rely on integration reload triggered by options_update_listener.
    # async def async_update(self) -> None:
    #    """Update the sensor."""
    #    self._update_surcharge_value()


class SurchargeOreSensor(SurchargeDisplaySensorBase):
    """Sensor to display the configured surcharge in öre/kWh."""

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._attr_name = "Spotpris påslag Öre /kWh"
        # Define an object_id for consistency, HA might still use slug of name
        self._attr_object_id = f"elpris_paslag_ore_{price_area.lower()}"
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_object_id}"
        self._attr_native_unit_of_measurement = "öre/kWh"
        self._attr_suggested_display_precision = ORE_ROUNDING_DECIMALS
        super().__init__(entry, price_area)


    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value to the surcharge in öre."""
        self._attr_native_value = round(self._get_surcharge_ore_from_config(), ORE_ROUNDING_DECIMALS)
        _LOGGER.debug(f"{self.name}: Updated surcharge value to {self._attr_native_value} öre/kWh")


class SurchargeSEKSensor(SurchargeDisplaySensorBase):
    """Sensor to display the configured surcharge in SEK/kWh."""

    def __init__(self, entry: ConfigEntry, price_area: str):
        self._attr_name = "Spotpris påslag SEK /kWh"
        self._attr_object_id = f"elpris_paslag_sek_{price_area.lower()}"
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_object_id}"
        self._attr_native_unit_of_measurement = "SEK/kWh"
        self._attr_suggested_display_precision = SEK_ROUNDING_DECIMALS
        super().__init__(entry, price_area)

    def _update_surcharge_value(self) -> None:
        """Update the sensor's native value to the surcharge in SEK."""
        surcharge_ore = self._get_surcharge_ore_from_config()
        self._attr_native_value = round(surcharge_ore / 100.0, SEK_ROUNDING_DECIMALS)
        _LOGGER.debug(f"{self.name}: Updated surcharge value to {self._attr_native_value} SEK/kWh")