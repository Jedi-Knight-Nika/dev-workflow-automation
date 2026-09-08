import pytest
from pydantic_settings.exceptions import SettingsError

from app.platform.configuration.settings import Settings


def test_blank_optional_json_environment_uses_defaults(monkeypatch):
    for key in ("V2_VALIDATION_COMMANDS", "SLACK_TEAM_ROUTES", "GITHUB_ISSUE_ROUTES"):
        monkeypatch.setenv(key, "")
    settings = Settings(_env_file=None)
    assert settings.v2_validation_commands == {}
    assert settings.slack_team_routes == {}
    assert settings.github_issue_routes == {}


def test_populated_json_is_not_ignored(monkeypatch):
    monkeypatch.setenv("V2_VALIDATION_COMMANDS", '{"repo":[["git","diff","--check"]]}')
    assert Settings(_env_file=None).v2_validation_commands == {"repo": [["git", "diff", "--check"]]}
    monkeypatch.setenv("V2_VALIDATION_COMMANDS", '{"repo":[]}}')
    with pytest.raises(SettingsError):
        Settings(_env_file=None)
