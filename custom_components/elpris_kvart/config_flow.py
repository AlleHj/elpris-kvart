# Version: 2025-05-21-rev13
"""Config flow for Elpris Kvart integration."""

import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_PRICE_AREA,
    CONF_SURCHARGE_ORE,
    DEFAULT_PRICE_AREA,
    DEFAULT_SURCHARGE_ORE,
    PRICE_AREAS,
)

_LOGGER = logging.getLogger(__name__)


class ElprisKvartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elpris Kvart."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def _validate_input(self, user_input: dict) -> bool:
        """Validate the user input."""
        if user_input[CONF_PRICE_AREA] not in PRICE_AREAS:
            _LOGGER.error(f"Invalid price area: {user_input[CONF_PRICE_AREA]}")
            return False
        try:
            surcharge = float(user_input[CONF_SURCHARGE_ORE])
            if surcharge < 0:
                _LOGGER.error(f"Invalid surcharge (negative): {surcharge}")
                return False
        except ValueError:
            _LOGGER.error(
                f"Invalid surcharge (not a number): {user_input[CONF_SURCHARGE_ORE]}"
            )
            return False
        return True

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            price_area = user_input[CONF_PRICE_AREA]

            # Config entry unique ID is based on price_area
            await self.async_set_unique_id(f"elpris_kvart_config_{price_area.lower()}")
            self._abort_if_unique_id_configured()

            if await self._validate_input(user_input):
                return self.async_create_entry(
                    title=f"Elpris Timme ({price_area})", data=user_input
                )
            errors["base"] = "invalid_input"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_PRICE_AREA, default=DEFAULT_PRICE_AREA): vol.In(
                    PRICE_AREAS
                ),
                vol.Required(
                    CONF_SURCHARGE_ORE, default=DEFAULT_SURCHARGE_ORE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="öre",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "surcharge_help_text": "Ange ditt elpåslag i öre per kWh (t.ex. 1.25 för 1,25 öre). Detta påslag kommer att adderas till spotpriset."
            },
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
        self.current_surcharge = self.config_entry.options.get(
            CONF_SURCHARGE_ORE,
            self.config_entry.data.get(CONF_SURCHARGE_ORE, DEFAULT_SURCHARGE_ORE),
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
                    updated_options = {**self.config_entry.options}
                    updated_options[CONF_SURCHARGE_ORE] = surcharge
                    return self.async_create_entry(title="", data=updated_options)
            except ValueError:
                errors["base"] = "invalid_surcharge_format"

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SURCHARGE_ORE, default=self.current_surcharge
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        step=0.01,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="öre",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
            description_placeholders={
                "surcharge_help_text": "Ändra ditt elpåslag i öre per kWh."
            },
        )
