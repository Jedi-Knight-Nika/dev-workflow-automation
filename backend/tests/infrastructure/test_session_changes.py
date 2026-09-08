import tomllib
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.agent_runtime.application.sessions import SessionConflict
from app.agent_runtime.domain.session_changes import can_keep_native, handoff_request
from app.agent_runtime.infrastructure.versions import HARNESS_VERSIONS
from app.bootstrap.engineering import session_administration
from app.interfaces.http.routes.engineering import router


def test_session_versions_match_locked_runner_dependency_pins() -> None:
    manifest = tomllib.loads(Path("pyproject.toml").read_text())
    dependencies = manifest["project"]["optional-dependencies"]["harness"]
    assert f"openai-codex=={HARNESS_VERSIONS['codex']}" in dependencies
    assert f"claude-agent-sdk=={HARNESS_VERSIONS['claude']}" in dependencies


def test_only_verified_codex_model_switch_can_retain_native_history() -> None:
    assert can_keep_native("codex", "codex", "openai", "openai")
    assert not can_keep_native("codex", "claude", "openai", "anthropic")
    assert not can_keep_native("claude", "claude", "anthropic", "anthropic")
    assert not can_keep_native("codex", "codex", "openai", "other")


def test_handoff_preserves_current_requirements_feedback_and_bounds_advisory_summary() -> None:
    result = handoff_request("Current requirements", "old" * 10000, "Switch requested", "Fix tests")
    assert "Current requirements" in result and "Fix tests" in result
    assert "Switch requested" in result and "not imported" in result
    assert len(result) < 5000
    with pytest.raises(ValueError, match="shorten them explicitly"):
        handoff_request("x" * 24000, "", "Switch", "New requirements must not be lost")


@pytest.mark.asyncio
async def test_session_api_is_metadata_only_and_rejects_untrusted_overrides() -> None:
    store = AsyncMock()
    store.read.return_value = None
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[session_administration] = lambda: store
    task_id, session_id = uuid4(), uuid4()
    body = {
        "session_id": str(session_id),
        "lifecycle_version": 2,
        "profile_version": 3,
        "mode": "handoff",
        "reason": "Switch harness explicitly",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"/tasks/{task_id}/session")).json() is None
        for extra in ("model", "provider", "native_session_id", "hard_budget_usd", "api_key"):
            response = await client.post(
                f"/tasks/{task_id}/session/change", json={**body, extra: "unsafe"}
            )
            assert response.status_code == 422
        for changes in ({"mode": "automatic"}, {"profile_version": 0}, {"reason": "   "}):
            response = await client.post(
                f"/tasks/{task_id}/session/change", json={**body, **changes}
            )
            assert response.status_code == 422
        store.change.assert_not_called()
        for error, status in (
            (SessionConflict("Reload first"), 409),
            (LookupError("Missing task"), 404),
            (ValueError("Too long"), 422),
        ):
            store.change.side_effect = error
            response = await client.post(f"/tasks/{task_id}/session/change", json=body)
            assert response.status_code == status
        command = store.change.await_args.args[1]
        assert command.session_id == session_id
        assert set(asdict(command)) == set(body)
