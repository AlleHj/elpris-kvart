# Version: 2026-05-15 - Moderniserad conftest med strikt tidszonsåterställning och raderat trådhack.
"""Global fixtures for elpris_kvart integration tests."""

from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def restore_timezone():
    """Säkerställer att tidszonen alltid återställs efter varje test för att förhindra läckage."""
    default_tz = dt_util.DEFAULT_TIME_ZONE
    yield
    dt_util.DEFAULT_TIME_ZONE = default_tz


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