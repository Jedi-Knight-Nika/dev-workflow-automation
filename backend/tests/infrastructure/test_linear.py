import hashlib
import hmac
import time
from typing import Any

import httpx
import pytest

from app.db.models import TaskState
from app.domain.webhooks.linear import (
    configured_repository_id,
    issue_labels,
    linear_comment,
    linear_priority,
)
from app.infrastructure.external_task_sync import external_status_configuration_key
from app.integrations.linear import LinearClient, verify_linear_signature


def test_linear_signature_and_timestamp_are_verified() -> None:
    body = b'{"type":"Issue"}'
    secret = "webhook-secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    now = round(time.time() * 1000)

    assert verify_linear_signature(body, secret, signature, now)
    assert not verify_linear_signature(body, secret, signature, now - 61_000)
    assert not verify_linear_signature(body + b" ", secret, signature, now)


def test_linear_payload_helpers_handle_supported_shapes() -> None:
    assert issue_labels({"labels": {"nodes": [{"name": "AI Ready"}]}}) == {"AI Ready"}
    assert issue_labels({"labels": [{"name": "Backend"}]}) == {"Backend"}
    assert linear_priority(1) == 1
    assert linear_priority(4) == 4
    assert linear_priority("urgent") == 3
    assert configured_repository_id({"repository_id": "invalid"}) is None


def test_linear_comment_is_normalized_for_intake() -> None:
    result = linear_comment(
        {
            "type": "Comment",
            "action": "create",
            "data": {
                "body": "Do not implement caching yet.",
                "issue": {"identifier": "CIT-42"},
                "user": {"name": "Nika"},
            },
        }
    )
    assert result is not None
    assert result[0] == "CIT-42"
    assert result[1]["raw_text"] == "Do not implement caching yet."


def test_linear_state_mapping_covers_operational_lifecycle() -> None:
    assert external_status_configuration_key("linear", TaskState.NEW) == "todo_state_id"
    assert (
        external_status_configuration_key("linear", TaskState.IMPLEMENTING)
        == "in_progress_state_id"
    )
    assert (
        external_status_configuration_key("linear", TaskState.WAITING_GITHUB)
        == "in_review_state_id"
    )
    assert external_status_configuration_key("linear", TaskState.NEEDS_HUMAN) == "blocked_state_id"
    assert (
        external_status_configuration_key("linear", TaskState.MERGED)
        == "ready_for_testing_state_id"
    )
    assert external_status_configuration_key("linear", TaskState.CANCELLED) == "done_state_id"
    assert (
        external_status_configuration_key("trello", TaskState.IMPLEMENTING) == "in_progress_list_id"
    )


@pytest.mark.asyncio
async def test_linear_issue_state_update_uses_graphql_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.linear.app/graphql"
        assert request.headers["authorization"] == "linear-key"
        assert b'"id":"CIT-42"' in request.content
        assert b'"stateId":"state-uuid"' in request.content
        return httpx.Response(200, json={"data": {"issueUpdate": {"success": True}}})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    await LinearClient("linear-key").update_issue_state("CIT-42", "state-uuid")


@pytest.mark.asyncio
async def test_linear_graphql_errors_are_not_treated_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"errors": [{"message": "Not allowed"}]})
    )
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with pytest.raises(RuntimeError, match="Not allowed"):
        await LinearClient("linear-key").update_issue_state("CIT-42", "state-uuid")


@pytest.mark.asyncio
async def test_linear_workflow_states_are_discovered_and_sorted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert b"workflowStates" in request.content
        return httpx.Response(
            200,
            json={
                "data": {
                    "workflowStates": {
                        "nodes": [
                            {
                                "id": "done",
                                "name": "Ready for Testing",
                                "type": "completed",
                                "team": {"id": "b", "name": "Web", "key": "WEB"},
                            },
                            {
                                "id": "started",
                                "name": "In Progress",
                                "type": "started",
                                "team": {"id": "a", "name": "API", "key": "API"},
                            },
                        ]
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    states = await LinearClient("linear-key").list_workflow_states()
    assert [state["id"] for state in states] == ["started", "done"]
    assert states[1]["team_key"] == "WEB"


@pytest.mark.asyncio
async def test_linear_connections_follow_opaque_cursors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursors: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.content.decode()
        cursor = "page-2" if '"after":"page-2"' in payload else None
        cursors.append(cursor)
        return httpx.Response(
            200,
            json={
                "data": {
                    "users": {
                        "nodes": [
                            {
                                "id": "user-2" if cursor else "user-1",
                                "name": "Zed" if cursor else "Alice",
                                "email": "",
                                "active": True,
                            }
                        ],
                        "pageInfo": {
                            "hasNextPage": cursor is None,
                            "endCursor": "page-2" if cursor is None else None,
                        },
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    members = await LinearClient("linear-key").list_members()

    assert cursors == [None, "page-2"]
    assert [member["id"] for member in members] == ["user-1", "user-2"]
