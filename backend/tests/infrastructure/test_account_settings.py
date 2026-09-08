import pytest
from pydantic import ValidationError

from app.interfaces.http.schemas.settings import GeneralSettings


def test_general_settings_accept_an_iana_timezone() -> None:
    settings = GeneralSettings(display_name="Nika", timezone="Asia/Tbilisi")

    assert settings.timezone == "Asia/Tbilisi"


def test_general_settings_reject_an_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        GeneralSettings(display_name="Nika", timezone="Mars/Olympus")
