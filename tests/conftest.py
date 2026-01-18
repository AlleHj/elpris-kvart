"""Global fixtures for elpris_kvart integration tests."""
from unittest.mock import patch
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield

@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield

# Denna fixture mockar API-anropen så vi kan kontrollera datan
@pytest.fixture(name="mock_elpris_api")
def mock_elpris_api_fixture():
    """Mocka elprisetjustnu.se API."""
    with patch("custom_components.elpris_kvart.ElprisApi.get_prices") as mock_get_prices:
        yield mock_get_prices
