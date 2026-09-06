import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent_runtime import router
from app.application.ports.agent_runtime import AgentRuntimeNotFound
from app.bootstrap.dependencies import get_agent_runtime_store


class FakeAgentRuntimeStore:
    def __init__(self) -> None:
        self.overrides: dict[str, Any] = {}

    async def effective(self, agent_id: uuid.UUID) -> dict[str, Any]:
        return self._view(agent_id)

    async def update(self, agent_id: uuid.UUID, overrides: dict[str, Any]) -> dict[str, Any]:
        if "temperature" in overrides:
            raise ValueError("Selected model does not support a temperature override")
        self.overrides = dict(overrides)
        return self._view(agent_id)

    async def reset(self, agent_id: uuid.UUID) -> dict[str, Any]:
        self.overrides = {}
        return self._view(agent_id)

    def _view(self, agent_id: uuid.UUID) -> dict[str, Any]:
        return {
            "agent_id": str(agent_id),
            "role_name": "Reviewer",
            "overrides": self.overrides,
            "override_policy": {"reasoning_level": "ALLOW_WITHIN_RANGE"},
            "effective": {"reasoning_level": self.overrides.get("reasoning_level", "HIGH")},
            "sources": {
                "reasoning_level": "AGENT" if "reasoning_level" in self.overrides else "ROLE"
            },
        }


def client_for(store: FakeAgentRuntimeStore) -> TestClient:
    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_agent_runtime_store] = lambda: store
    return TestClient(application)


def test_runtime_update_returns_effective_configuration_and_sources() -> None:
    agent_id = uuid.uuid4()
    store = FakeAgentRuntimeStore()

    response = client_for(store).put(
        f"/api/v1/agent-runtime/{agent_id}/overrides",
        json={"reasoning_level": "MEDIUM"},
    )

    assert response.status_code == 200
    assert response.json()["overrides"] == {"reasoning_level": "MEDIUM"}
    assert response.json()["effective"]["reasoning_level"] == "MEDIUM"
    assert response.json()["sources"]["reasoning_level"] == "AGENT"


def test_runtime_reset_removes_explicit_overrides() -> None:
    agent_id = uuid.uuid4()
    store = FakeAgentRuntimeStore()
    store.overrides = {"reasoning_level": "MEDIUM"}

    response = client_for(store).delete(f"/api/v1/agent-runtime/{agent_id}/overrides")

    assert response.status_code == 200
    assert response.json()["overrides"] == {}
    assert response.json()["effective"]["reasoning_level"] == "HIGH"
    assert response.json()["sources"]["reasoning_level"] == "ROLE"


def test_runtime_incompatibility_is_a_validation_error() -> None:
    agent_id = uuid.uuid4()

    response = client_for(FakeAgentRuntimeStore()).put(
        f"/api/v1/agent-runtime/{agent_id}/overrides",
        json={"temperature": 0.2},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == ("Selected model does not support a temperature override")


def test_missing_agent_returns_not_found() -> None:
    class MissingAgentStore(FakeAgentRuntimeStore):
        async def effective(self, agent_id: uuid.UUID) -> dict[str, Any]:
            raise AgentRuntimeNotFound("Agent not found")

    response = client_for(MissingAgentStore()).get(f"/api/v1/agent-runtime/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"
