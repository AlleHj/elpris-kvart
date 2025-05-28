# Version: 2025-05-28-v0.1.3
"""Config flow for Elpris Timme integration."""
import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv # Importera cv

from .const import (
    DOMAIN,
    CONF_PRICE_AREA,
    CONF_SURCHARGE_ORE,
    DEFAULT_PRICE_AREA,
    DEFAULT_SURCHARGE_ORE,
    PRICE_AREAS,
    CONF_DEBUG_MODE, # Ny
    DEFAULT_DEBUG_MODE, # Ny
)

_LOGGER = logging.getLogger(__name__)

class ElprisTimmeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elpris Timme."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def _validate_input(self, user_input: dict) -> str | None:
        """Validate the user input."""
        if user_input[CONF_PRICE_AREA] not in PRICE_AREAS:
            _LOGGER.error(f"Invalid price area: {user_input[CONF_PRICE_AREA]}")
            return "invalid_input" # Ändrad för att matcha error i strings.json
        try:
            surcharge = float(user_input[CONF_SURCHARGE_ORE])
            if surcharge < 0:
                 _LOGGER.error(f"Invalid surcharge (negative): {surcharge}")
                 return "invalid_input" # Ändrad
        except ValueError:
            _LOGGER.error(f"Invalid surcharge (not a number): {user_input[CONF_SURCHARGE_ORE]}")
            return "invalid_input" # Ändrad
        return None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        # Hämta dokumentationslänk från manifest
        # Denna kontrollerar om self.hass.data["integrations"][DOMAIN] finns, annars default
        component = self.hass.data.get("integrations", {}).get(DOMAIN)
        docs_url = component.manifest.get("documentation") if component and component.manifest else ""


        if user_input is not None:
            price_area = user_input[CONF_PRICE_AREA]

            await self.async_set_unique_id(f"elpris_timme_config_{price_area.lower()}")
            self._abort_if_unique_id_configured(error="already_configured") # Lägg till error key

            validation_error = await self._validate_input(user_input)
            if not validation_error:
                # Spara initial debug mode som False (eller från DEFAULT_DEBUG_MODE)
                # Detta säkerställer att options har ett värde för debug_mode från start
                initial_options = {
                    CONF_DEBUG_MODE: DEFAULT_DEBUG_MODE,
                    CONF_SURCHARGE_ORE: user_input[CONF_SURCHARGE_ORE] # Behåll påslag från setup
                }
                return self.async_create_entry(
                    title=f"Elpris Timme ({price_area})",
                    data=user_input,
                    options=initial_options
                )
            errors["base"] = validation_error

        data_schema = vol.Schema({
            vol.Required(CONF_PRICE_AREA, default=DEFAULT_PRICE_AREA): vol.In(PRICE_AREAS),
            vol.Required(
                CONF_SURCHARGE_ORE,
                default=DEFAULT_SURCHARGE_ORE
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="öre",
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"docs_url": docs_url} # Används i strings.json
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return ElprisTimmeOptionsFlowHandler(config_entry)


class ElprisTimmeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for Elpris Timme."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        # Hämta befintliga options, eller data om options inte finns, eller default
        self.current_surcharge = config_entry.options.get(
            CONF_SURCHARGE_ORE, config_entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE)
        )
        self.current_debug_mode = config_entry.options.get(
            CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE
        )

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            try:
                surcharge = float(user_input[CONF_SURCHARGE_ORE])
                if surcharge < 0:
                    errors["base"] = "negative_surcharge"
                else:
                    # Behåll alla befintliga options och uppdatera bara de som finns i user_input
                    updated_options = {**self.config_entry.options}
                    updated_options[CONF_SURCHARGE_ORE] = surcharge
                    updated_options[CONF_DEBUG_MODE] = user_input[CONF_DEBUG_MODE]
                    return self.async_create_entry(title="", data=updated_options)
            except ValueError:
                errors["base"] = "invalid_surcharge_format"

        options_schema = vol.Schema({
            vol.Required(
                CONF_SURCHARGE_ORE,
                default=self.current_surcharge
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    step=0.01,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="öre",
                )
            ),
            vol.Optional( # Ändrad till Optional, default hanterar om den saknas
                CONF_DEBUG_MODE,
                default=self.current_debug_mode
            ): cv.boolean, # Använd cv.boolean för checkboxes
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors
            # description_placeholders kan läggas till här om det behövs för options-steget.
        )