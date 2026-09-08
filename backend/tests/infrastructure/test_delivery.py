import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.delivery.domain.merge import MergePolicy
from app.delivery.infrastructure.git_runner import GitManifest, copy_objects
from app.delivery.infrastructure.github import GitHubDelivery

SHA = "a" * 40


def fixture_payloads() -> dict[str, object]:
    return {
        "/repos/acme/repo/pulls/1": {
            "head": {"sha": SHA},
            "state": "open",
            "mergeable": True,
            "mergeable_state": "clean",
            "user": {"id": 7},
        },
        "/repos/acme/repo/pulls/1/reviews": [
            {"id": 20, "state": "APPROVED", "commit_id": SHA, "user": {"id": 10, "type": "User"}}
        ],
        f"/repos/acme/repo/commits/{SHA}/check-runs": {
            "check_runs": [
                {
                    "id": 1,
                    "name": "test",
                    "head_sha": SHA,
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        },
        f"/repos/acme/repo/commits/{SHA}/statuses": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,actor,formal,approved",
    [
        (f"/lgtm {SHA}", 10, False, True),
        ("lgtm", 10, False, False),
        (f"/lgtm {'b' * 40}", 10, False, False),
        (f"/lgtm {SHA}", 99, False, False),
        (f"/lgtm {SHA}", 10, True, False),
    ],
)
async def test_lgtm_requires_explicit_policy_exact_sha_and_trusted_actor(
    body: str, actor: int, formal: bool, approved: bool
) -> None:
    data = fixture_payloads()
    data["/repos/acme/repo/pulls/1/reviews"] = []
    data["/repos/acme/repo/issues/1/comments"] = [
        {"id": 30, "body": body, "user": {"id": actor, "type": "User"}}
    ]
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=data[request.url.path])
        ),
    ) as client:
        policy = MergePolicy(True, True, frozenset({"10"}), formal)
        evidence, _ = await GitHubDelivery(client, "acme", "repo").evidence(
            1, SHA, SHA, policy, ("test",), runnable=True
        )
        assert (not policy.blockers(evidence)) == approved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,expected",
    [
        (None, ()),
        ("old_approval", ("APPROVAL_MISSING",)),
        ("missing_check", ("CHECKS_NOT_GREEN",)),
        ("changes_requested", ("BLOCKING_REVIEW", "APPROVAL_MISSING")),
        ("untrusted", ("APPROVAL_MISSING",)),
    ],
)
async def test_merge_evidence_requires_current_trusted_approval_and_ci(
    failure: str | None, expected: tuple[str, ...]
) -> None:
    data = fixture_payloads()
    reviews = data["/repos/acme/repo/pulls/1/reviews"]
    assert isinstance(reviews, list)
    if failure == "old_approval":
        reviews[0]["commit_id"] = "b" * 40
    elif failure == "changes_requested":
        reviews.append({**reviews[0], "id": 21, "state": "CHANGES_REQUESTED"})
    elif failure == "missing_check":
        data[f"/repos/acme/repo/commits/{SHA}/check-runs"] = {"check_runs": []}
    elif failure == "untrusted":
        reviews[0]["user"]["id"] = 99
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=data[request.url.path])
        ),
    ) as client:
        policy = MergePolicy(True, True, frozenset({"10"}))
        evidence, _ = await GitHubDelivery(client, "acme", "repo").evidence(
            1, SHA, SHA, policy, ("test",), runnable=True
        )
        assert policy.blockers(evidence) == expected


@pytest.mark.asyncio
async def test_merge_sends_expected_sha_and_never_retries_a_write() -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert json.loads(request.content) == {"sha": SHA, "merge_method": "squash"}
        return httpx.Response(409, json={"message": "Head changed"})

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await GitHubDelivery(client, "acme", "repo").merge(1, SHA)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_publish_recovers_a_pull_request_with_the_conventional_commit_title() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/pulls"):
            return httpx.Response(200, json=[{"number": 1}])
        if request.method == "GET":
            return httpx.Response(200, json={"number": 1, "title": "Work item", "head": {"sha": SHA}})
        assert request.method == "PATCH"
        assert json.loads(request.content) == {"title": "fix(api): handle timeout"}
        return httpx.Response(
            200,
            json={"number": 1, "title": "fix(api): handle timeout", "head": {"sha": SHA}},
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(respond)
    ) as client:
        pull = await GitHubDelivery(client, "acme", "repo").publish(
            branch="agent/task-1",
            base="main",
            title="fix(api): handle timeout",
            body="Task: API-1",
            owner="acme",
            expected_sha=SHA,
        )

    assert pull["title"] == "fix(api): handle timeout"
    assert [request.method for request in requests] == ["GET", "GET", "PATCH"]


def test_git_transfer_excludes_alternates_and_rejects_symlinks(tmp_path: Path) -> None:
    source, target = tmp_path / "objects", tmp_path / "clean-objects"
    (source / "info").mkdir(parents=True)
    (source / "info" / "alternates").write_text("/private/controller-secrets")
    (source / "aa").mkdir()
    (source / "aa" / "bb").write_bytes(b"object")
    copy_objects(source, target)
    assert (target / "aa" / "bb").read_bytes() == b"object"
    assert not (target / "info").exists()
    (source / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlinks"):
        copy_objects(source, target)


def test_git_manifest_cannot_target_default_branch_or_arbitrary_remote() -> None:
    with pytest.raises(ValueError):
        GitManifest(
            operation="publish",
            owner="acme",
            repository="repo",
            branch="main",
            base_branch="main",
            expected_sha=SHA,
        )
    with pytest.raises(ValueError):
        GitManifest(
            operation="prepare",
            owner="https://attacker",
            repository="repo",
            branch=f"agent/task-{uuid4()}",
            base_branch="main",
        )
