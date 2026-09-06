from typing import Any

import httpx
import pytest

from app.integrations.github import GitHubClient, decode_actions_log


@pytest.mark.asyncio
async def test_repository_discovery_follows_github_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        count = 100 if page == 1 else 1
        return httpx.Response(
            200,
            json=[
                {
                    "id": page * 1000 + index,
                    "owner": {"login": "acme"},
                    "name": f"service-{page}-{index}",
                    "full_name": f"acme/service-{page}-{index}",
                    "clone_url": "https://github.com/acme/service.git",
                    "default_branch": "main",
                    "private": True,
                }
                for index in range(count)
            ],
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    repositories = await GitHubClient("secret").list_repositories()

    assert len(repositories) == 101
    assert [request.url.params["page"] for request in requests] == ["1", "2"]


@pytest.mark.asyncio
async def test_existing_branch_pull_request_can_be_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["head"] == "acme:agent/task"
        return httpx.Response(
            200,
            json=[
                {
                    "number": 17,
                    "html_url": "https://github.com/acme/service/pull/17",
                    "state": "open",
                    "head": {"sha": "abc123"},
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").find_open_pull_request("acme", "service", "agent/task")

    assert result is not None
    assert result.number == 17


@pytest.mark.asyncio
async def test_create_pull_request_maps_github_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/service/pulls"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            201,
            json={
                "number": 17,
                "html_url": "https://github.com/acme/service/pull/17",
                "state": "open",
                "head": {"sha": "abc123"},
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").create_pull_request(
        "acme", "service", "agent/task", "main", "Fix task", "Body"
    )

    assert result.number == 17
    assert result.head_sha == "abc123"


@pytest.mark.asyncio
async def test_merge_pull_request_sends_expected_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/service/pulls/17/merge"
        assert b'"sha":"abc123"' in request.content
        assert b'"merge_method":"squash"' in request.content
        return httpx.Response(200, json={"merged": True, "sha": "merged456", "message": "ok"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").merge_pull_request("acme", "service", 17, "abc123")

    assert result.merged is True
    assert result.sha == "merged456"


@pytest.mark.asyncio
async def test_get_pull_request_maps_merge_reconciliation_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "number": 17,
                "html_url": "https://github.com/acme/service/pull/17",
                "state": "closed",
                "head": {"sha": "head123"},
                "merged": True,
                "merge_commit_sha": "merge456",
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").get_pull_request("acme", "service", 17)

    assert result.merged is True
    assert result.merge_commit_sha == "merge456"


def test_actions_log_extraction_prefers_failure_lines_and_is_bounded() -> None:
    content = (
        "ordinary output\n" * 100 + "AssertionError: expected 2\nFAILED test_api.py\n"
    ).encode()

    result = decode_actions_log(content, max_chars=80)

    assert "AssertionError" in result
    assert "FAILED test_api.py" in result
    assert "ordinary output" not in result


@pytest.mark.asyncio
async def test_check_diagnostics_fetches_annotations_and_actions_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/annotations"):
            return httpx.Response(200, json=[{"path": "api.py", "message": "failure"}])
        if request.url.path.endswith("/actions/jobs/991/logs"):
            return httpx.Response(200, content=b"ERROR test failed")
        return httpx.Response(
            200,
            json={
                "id": 55,
                "external_id": "991",
                "app": {"slug": "github-actions"},
                "output": {"summary": "failed"},
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").get_check_run_diagnostics("acme", "service", 55)

    assert result["annotations"][0]["path"] == "api.py"
    assert result["actions_log"] == "ERROR test failed"


@pytest.mark.asyncio
async def test_revision_evidence_fetches_checks_statuses_and_current_reviews(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/check-runs"):
            return httpx.Response(
                200,
                json={
                    "check_runs": [
                        {
                            "name": "CI",
                            "conclusion": "success",
                            "head_sha": "head-sha",
                            "details_url": "https://example.test/ci",
                        }
                    ]
                },
            )
        if path.endswith("/status"):
            return httpx.Response(200, json={"statuses": []})
        if path.endswith("/reviews"):
            return httpx.Response(
                200,
                json=[
                    {
                        "state": "APPROVED",
                        "commit_id": "head-sha",
                        "user": {"login": "reviewer"},
                    },
                    {"state": "CHANGES_REQUESTED", "commit_id": "stale-sha"},
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "commit_id": "head-sha",
                    "body": "Fix this",
                    "user": {"login": "bot"},
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    result = await GitHubClient("secret").list_revision_evidence("acme", "service", 17, "head-sha")

    assert [(item["kind"], item["status"]) for item in result] == [
        ("CHECK", "SUCCESS"),
        ("REVIEW", "APPROVED"),
        ("REVIEW_COMMENT", "ACTION_REQUIRED"),
    ]
