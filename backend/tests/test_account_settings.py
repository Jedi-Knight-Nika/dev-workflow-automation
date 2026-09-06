import pytest
from pydantic import ValidationError

from app.schemas.settings import GeneralSettings, StorageSettings


def test_general_settings_accept_an_iana_timezone() -> None:
    settings = GeneralSettings(display_name="Nika", timezone="Asia/Tbilisi")

    assert settings.timezone == "Asia/Tbilisi"


def test_general_settings_reject_an_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        GeneralSettings(display_name="Nika", timezone="Mars/Olympus")


def test_storage_hard_stop_cannot_be_lower_than_warning() -> None:
    with pytest.raises(ValidationError, match="hard stop"):
        StorageSettings(monthly_cost_warning=100, monthly_cost_hard_stop=50)
