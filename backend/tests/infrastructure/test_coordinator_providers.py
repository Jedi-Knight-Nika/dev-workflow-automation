import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.coordinator.application.ports import ConversationUnavailable
from app.platform.integrations.infrastructure.conversations import ProviderConversations


async def test_provider_read_failure_is_translated_at_adapter_boundary(monkeypatch):
    gateway = ProviderConversations(AsyncMock())
    monkeypatch.setattr(
        gateway, "_read", AsyncMock(side_effect=httpx.ReadTimeout("authorization=secret"))
    )
    with pytest.raises(ConversationUnavailable, match="^ReadTimeout$"):
        await gateway.read(uuid4(), "github", "READ_TASK")


@pytest.mark.parametrize("provider", ["github", "trello", "linear", "slack"])
async def test_replies_use_bound_task_destination_and_return_effect_identity(provider, monkeypatch):
    gateway = ProviderConversations(AsyncMock())
    root = {
        "github": "https://api.github.com/repos/acme/repo",
        "trello": "https://api.trello.com/1",
        "linear": "https://api.linear.app/graphql",
        "slack": "https://slack.com/api",
    }[provider]
    monkeypatch.setattr(
        gateway,
        "_target",
        AsyncMock(
            return_value=(
                root,
                {"Authorization": "test"},
                {"id": "bound-card", "number": 42, "channel": "C1", "ts": "1.2"},
            )
        ),
    )
    response = {
        "id": "effect-1",
        "ts": "effect-1",
        "ok": True,
        "data": {"commentCreate": {"success": True, "comment": {"id": "effect-1"}}},
    }
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=response)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handle))
    )
    assert await gateway.reply(uuid4(), provider, "Approved scope", uuid4()) == "effect-1"
    assert len(calls) == 1 and calls[0].method == "POST"
    if provider == "slack":
        body = json.loads(calls[0].content)
        assert body["thread_ts"] == "1.2" and body["channel"] == "C1"
    if provider == "github":
        assert calls[0].url.path == "/repos/acme/repo/issues/42/comments"


async def test_slack_http_success_with_api_failure_is_rejected(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(
            **kw,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"ok": False, "error": "invalid_auth"})
            ),
        ),
    )
    with pytest.raises(ValueError, match="rejected"):
        await ProviderConversations.verify_identity("slack", "test-token")


@pytest.mark.parametrize(
    "changed,already_requested", [(False, False), (True, False), (False, True)]
)
async def test_review_request_is_scoped_to_current_sha_and_configured_ids(
    changed, already_requested
):
    from app.platform.integrations.infrastructure.github_coordination import request_review

    pull = {
        "state": "open",
        "head": {"sha": "new" if changed else "current"},
        "user": {"id": 1},
        "requested_reviewers": [{"id": 2}] if already_requested else [],
    }
    request = AsyncMock(
        side_effect=[pull]
        if changed or already_requested
        else [
            pull,
            {"id": 2, "login": "reviewer", "type": "User"},
            pull,
            {"requested_reviewers": [{"id": 2}]},
        ]
    )
    if changed:
        with pytest.raises(ValueError, match="revision"):
            await request_review(
                request,
                "https://api.github.com/repos/org/repo",
                {},
                {"number": 5, "sha": "current"},
                ("2",),
            )
    else:
        await request_review(
            request,
            "https://api.github.com/repos/org/repo",
            {},
            {"number": 5, "sha": "current"},
            ("2",),
        )
    posts = [call for call in request.await_args_list if call.args[0] == "POST"]
    assert len(posts) == int(not changed and not already_requested)
    if posts:
        assert posts[0].kwargs["json"] == {"reviewers": ["reviewer"]}


@pytest.mark.parametrize(
    "actor,age,matches", [("self", 1, 1), ("human", 1, 0), ("self", -60, 0), ("self", 1, 2)]
)
async def test_delivery_confirmation_requires_own_recent_unique_message(
    actor, age, matches, monkeypatch
):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    sessions = MagicMock()
    session = AsyncMock()
    sessions.return_value.__aenter__.return_value = session
    session.scalar.return_value = type(
        "Integration", (), {"configuration": {"identity_id": "self"}}
    )()
    gateway = ProviderConversations(sessions)
    now = datetime.now(UTC)
    row = {
        "id": "sent",
        "text": "Exact reply",
        "actor": actor,
        "created_at": (now + timedelta(seconds=age)).isoformat(),
    }
    monkeypatch.setattr(
        gateway, "read", AsyncMock(return_value={"messages": [row] * max(1, matches)})
    )
    result = await gateway.reconcile(uuid4(), "trello", "Exact reply", uuid4(), now, "REPLY")
    assert result == ("sent" if matches == 1 else None)
