"""Test elpris_kvart config flow."""
from unittest.mock import patch
import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.elpris_kvart.const import (
    DOMAIN,
    CONF_PRICE_AREA,
    CONF_SURCHARGE_ORE,
    PRICE_AREAS,
)

# Testfall 1: Framgångsrik installation av integrationen
# Förklaring: Detta test simulerar att användaren går igenom konfigurationsflödet
# och matar in giltiga värden (Prisområde SE3 och 0.0 i påslag).
# Vi verifierar att en konfigurationspost (entry) skapas korrekt.
async def test_successful_config_flow(hass: HomeAssistant) -> None:
    """Testa ett lyckat konfigurationsflöde."""

    # Initiera flödet
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Kontrollera att vi får upp ett formulär (step user)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Simulera att användaren fyller i formuläret
    with patch(
        "custom_components.elpris_kvart.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_PRICE_AREA: "SE3",
                CONF_SURCHARGE_ORE: 0.0,
            },
        )
        await hass.async_block_till_done()

    # Kontrollera att en entry skapades (CREATE_ENTRY)
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Elpris Kvart (SE3)"
    assert result2["data"] == {
        CONF_PRICE_AREA: "SE3",
        CONF_SURCHARGE_ORE: 0.0,
    }

    # Verifiera att setup startades
    assert len(mock_setup_entry.mock_calls) == 1


# Testfall 2: Validering av felaktigt påslag
# Förklaring: Detta test simulerar att användaren matar in ett negativt tal som påslag.
# Eftersom schemat har en spärr (min=0.0) kommer Home Assistant kasta ett InvalidData exception
# innan vår egen valideringslogik ens nås. Detta bekräftar dock att spärren fungerar.
async def test_invalid_surcharge(hass: HomeAssistant) -> None:
    """Testa att config flow hanterar felaktigt påslag."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Fyll i med negativt påslag. Vi förväntar oss ett InvalidData exception
    # eftersom schemat definierar min=0.0.
    try:
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_PRICE_AREA: "SE3",
                CONF_SURCHARGE_ORE: -1.0,
            },
        )
        pytest.fail("Borde ha kastat InvalidData pga schema-validering")
    except data_entry_flow.InvalidData as err:
        # Kontrollera att felet ligger på rätt fält
        assert "surcharge_ore" in str(err.schema_errors)
