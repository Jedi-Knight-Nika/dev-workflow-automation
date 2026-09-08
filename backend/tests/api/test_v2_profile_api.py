"""HTTP validation for fixed profiles; no database or provider calls."""

from dataclasses import asdict
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v2 import router
from app.bootstrap.v2 import team_profiles
from app.teams.application.profiles import ProfileConflict, ProfileView, TeamProfiles
from app.teams.domain.profiles import default_profiles


@pytest.fixture
def profile_api() -> tuple[TestClient, AsyncMock, ProfileView]:
    row = ProfileView(uuid4(), uuid4(), 1, default_profiles()[1])
    store = AsyncMock(spec=TeamProfiles)
    store.list_profiles.return_value = [row]
    store.save.return_value = row
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[team_profiles] = lambda: store
    return TestClient(app), store, row


def test_profiles_are_team_scoped_and_omit_credentials(profile_api: tuple) -> None:
    client, store, row = profile_api
    response = client.get(f"/v2/teams/{row.team_id}/profiles")
    assert response.status_code == 200
    assert response.json()[0]["model"] == "gpt-5.6-terra"
    assert "credentials" not in response.text
    store.list_profiles.assert_awaited_once_with(row.team_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"system_prompt": "override"},
        {"role_kind": "EXECUTOR"},
        {"enabled": False},
        {"model": ""},
        {"provider": "anthropic"},
        {"hard_budget_usd": -1},
    ],
)
def test_profiles_reject_uneditable_contract_or_invalid_model_pair(
    profile_api: tuple, changes: dict
) -> None:
    client, store, row = profile_api
    body = asdict(row.profile)
    body.pop("role_kind")
    body.pop("prompt_version")
    body.update(version=1, **changes)
    response = client.put(f"/v2/teams/{row.team_id}/profiles/DEVELOPER", json=body)
    assert response.status_code == 422
    store.save.assert_not_called()


def test_stale_profile_update_returns_conflict(profile_api: tuple) -> None:
    client, store, row = profile_api
    body = asdict(row.profile)
    body.pop("role_kind")
    body.pop("prompt_version")
    body["version"] = 1
    store.save.side_effect = ProfileConflict("Reload")
    assert client.put(f"/v2/teams/{row.team_id}/profiles/DEVELOPER", json=body).status_code == 409


def test_capabilities_do_not_claim_preview_is_executable(profile_api: tuple) -> None:
    client, _, _ = profile_api
    assert client.get("/v2/capabilities").json()["execution_ready"] is False


def test_web_terminal_routes_are_retired_but_history_tables_remain() -> None:
    from app.db.base import Base
    from app.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("/terminal" in path for path in paths)
    assert "terminal_sessions" in Base.metadata.tables
