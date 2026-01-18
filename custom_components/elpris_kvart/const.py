# Version: 2025-12-19-rev18
"""Constants for the Elpris Kvart integration."""

DOMAIN = "elpris_kvart"
PLATFORMS = ["sensor"]

# Integration Identity
INTEGRATION_NAME = "Elpris Kvart"
MANUFACTURER = "Custom Elpris"
MODEL = "Price API (SE)"

# Default configuration values
DEFAULT_PRICE_AREA = "SE4"
DEFAULT_SURCHARGE_ORE = 0.0
PRICE_AREAS = ["SE1", "SE2", "SE3", "SE4"]

# API details
API_BASE_URL = "https://www.elprisetjustnu.se/api/v1/prices"

# Configuration keys
CONF_PRICE_AREA = "price_area"
CONF_SURCHARGE_ORE = "surcharge_ore"  # Surcharge is always configured in öre

# Update timings
DAILY_FETCH_HOUR = 14
RETRY_INTERVAL_MINUTES = 30
NORMAL_UPDATE_INTERVAL_HOURS = 1

# Sensor attributes (Common)
ATTR_PRICE_AREA = "price_area"
ATTR_LAST_API_UPDATE = "last_api_data_update"
ATTR_RAW_TODAY = "raw_today"

# Attributes for ÖRE sensors
ATTR_TOMORROW_PRICES_ORE = "tomorrow_hourly_prices_ore"
ATTR_MIN_PRICE_TODAY_ORE = "min_price_today_ore"
ATTR_MAX_PRICE_TODAY_ORE = "max_price_today_ore"
ATTR_MIN_PRICE_TOMORROW_ORE = "min_price_tomorrow_ore"
ATTR_MAX_PRICE_TOMORROW_ORE = "max_price_tomorrow_ore"
ATTR_SPOT_PRICE_ORE_ON_SURCHARGE_SENSOR = "spot_price_ore"
ATTR_SURCHARGE_APPLIED_ORE_ON_SURCHARGE_SENSOR = "surcharge_applied_ore"

# Attributes for SEK sensors
ATTR_TOMORROW_PRICES_SEK = "tomorrow_hourly_prices_sek"
ATTR_MIN_PRICE_TODAY_SEK = "min_price_today_sek"
ATTR_MAX_PRICE_TODAY_SEK = "max_price_today_sek"
ATTR_MIN_PRICE_TOMORROW_SEK = "min_price_tomorrow_sek"
ATTR_MAX_PRICE_TOMORROW_SEK = "max_price_tomorrow_sek"
ATTR_SPOT_PRICE_SEK_ON_SURCHARGE_SENSOR = "spot_price_sek"
ATTR_SURCHARGE_APPLIED_SEK_ON_SURCHARGE_SENSOR = "surcharge_applied_sek"

# Icons
ICON_CURRENCY_SEK = "mdi:currency-sek"
ICON_SURCHARGE_DISPLAY = "mdi:cash-plus"
