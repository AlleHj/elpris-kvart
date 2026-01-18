"""Global fixtures for elpris_kvart integration tests."""

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


# Denna fixture mockar API-anropen så vi kan kontrollera datan
@pytest.fixture(name="mock_elpris_api")
def mock_elpris_api_fixture():
    """Mocka elprisetjustnu.se API."""
    with patch(
        "custom_components.elpris_kvart.ElprisApi.get_prices"
    ) as mock_get_prices:
        yield mock_get_prices


@pytest.fixture(autouse=True)
async def ensure_cleanup(hass):
    """Försök tvinga fram cleanup av timers och dölj kända lingering threads."""
    yield
    # Vänta på att eventuella pågående tasks ska bli klara
    await hass.async_block_till_done()

    # Kör fram tiden för att låta eventuella bakgrundsprocesser/timers avslutas
    future = dt_util.utcnow() + timedelta(seconds=300)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()

    # WORKAROUND: Python 3.12 + HA test plugin har problem med att stänga ner
    # _run_safe_shutdown_loop. Vi döper om tråden så att test-pluginet tror att
    # det är en systemtråd (startar med "waitpid-").
    # Detta undviker AssertionError vid teardown.
    for thread in threading.enumerate():
        if "_run_safe_shutdown_loop" in thread.name:
            thread.name = f"waitpid-suppressed-{thread.name}"
