"""Task-scoped provider operations. No model-selected URLs, credentials or destinations."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.coordinator.application.ports import ConversationUnavailable
from app.delivery.infrastructure.git_transport import github_token
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.intake.infrastructure.trello_client import parse_trello_credentials
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.repositories.infrastructure.models import Repository


class ProviderConversations:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def request_review(self, task_id: UUID, action_id: UUID) -> str:
        from app.platform.integrations.infrastructure.github_coordination import request_review
        from app.teams.infrastructure.automation import read_policy

        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            if not task or not task.team_id:
                raise ValueError("Review request requires a task Team")
            policy = await read_policy(session, task.team_id)
            repository = (
                await session.get(Repository, task.repository_id) if task.repository_id else None
            )
            if (
                not repository
                or not repository.enabled
                or repository.archived_at
                or repository.id not in policy.repository_ids
            ):
                raise ValueError("Repository review scope was revoked")
        root, headers, target = await self._target(task_id, "github")
        return await request_review(
            self._request, root, headers, target, policy.authorized_reviewer_ids
        )

    async def reconcile(
        self,
        task_id: UUID,
        provider: str,
        message: str,
        action_id: UUID,
        attempted_at: datetime,
        kind: str,
    ) -> str | None:
        """Read-only confirmation. Absence in a bounded excerpt never authorizes a resend."""
        if kind == "REQUEST_REVIEW":
            # A reviewer may already have responded or been removed. Inspect manually;
            # absence of a pending request does not mean our original POST failed.
            return None
        if provider in {"dashboard", "engineering"}:
            return f"dashboard:{action_id}"
        async with self.sessions() as session:
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == provider)
            )
            identity = (
                str((integration.configuration or {}).get("identity_id") or "")
                if integration
                else ""
            )
        if not identity and provider == "github":
            _, headers, _ = await self._target(task_id, provider)
            user = await self._request("GET", "https://api.github.com/user", headers)
            identity = str(user["id"])
        if not identity:
            return None
        evidence = await self.read(task_id, provider, "RECONCILE")
        matches = []
        for row in evidence.get("messages", []):
            if (
                row.get("actor") != identity
                or row.get("text") != message
                or not row.get("created_at")
            ):
                continue
            created = datetime.fromisoformat(row["created_at"])
            # Providers may round to seconds. Multiple matching messages stay uncertain.
            seconds = (created - attempted_at.replace(microsecond=0)).total_seconds()
            if 0 <= seconds <= 300:
                matches.append(str(row["id"]))
        return matches[0] if len(matches) == 1 else None

    async def _target(
        self, task_id: UUID, provider: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        async with self.sessions() as session:
            task = await session.get(Task, task_id)
            if not task:
                raise LookupError("Task not found")
            snapshot = await session.scalar(
                select(ExternalTaskSnapshot)
                .where(
                    ExternalTaskSnapshot.task_id == task_id,
                    ExternalTaskSnapshot.provider == provider,
                )
                .order_by(ExternalTaskSnapshot.synchronized_at.desc())
                .limit(1)
            )
            if provider == "github":
                repository = (
                    await session.get(Repository, task.repository_id)
                    if task.repository_id
                    else None
                )
                if not repository or not task.pull_request_number:
                    raise ValueError("Task has no published GitHub PR")
                token = await github_token(session)
                return (
                    f"https://api.github.com/repos/{repository.owner}/{repository.name}",
                    {
                        "Authorization": f"Bearer {token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    {"number": task.pull_request_number, "sha": task.current_revision},
                )
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == provider)
            )
            if not integration or not integration.encrypted_credentials or not snapshot:
                raise ValueError("Conversation provider is not configured for this task")
            credential = cipher.decrypt(integration.encrypted_credentials)
            if provider == "trello":
                value = parse_trello_credentials(credential)
                return (
                    "https://api.trello.com/1",
                    {
                        "Authorization": f'OAuth oauth_consumer_key="{value["api_key"]}", oauth_token="{value["token"]}"'
                    },
                    {"id": snapshot.external_id},
                )
            if provider == "linear":
                return (
                    "https://api.linear.app/graphql",
                    {"Authorization": credential},
                    {"id": snapshot.external_id},
                )
            if provider == "slack":
                _, channel, ts = snapshot.external_id.split(":", 2)
                return (
                    "https://slack.com/api",
                    {"Authorization": f"Bearer {credential}"},
                    {"channel": channel, "ts": ts},
                )
            raise ValueError("Unsupported conversation provider")

    @staticmethod
    async def _request(method: str, url: str, headers: dict[str, str], **kwargs: Any) -> Any:
        # Never automatically retry a message creation. Unknown delivery is visible.
        async with (
            httpx.AsyncClient(timeout=15, follow_redirects=False) as client,
            client.stream(method, url, headers=headers, **kwargs) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for part in response.aiter_bytes():
                body.extend(part)
                if len(body) > 256000:
                    raise ValueError("Provider conversation exceeds the response bound")
        data = json.loads(body)
        if isinstance(data, dict) and (data.get("ok") is False or data.get("errors")):
            raise ValueError(
                "Provider rejected the conversation operation; verify access and scopes"
            )
        return data

    @staticmethod
    async def verify_identity(provider: str, credential: str) -> dict[str, str]:
        request = ProviderConversations._request
        if provider == "trello":
            parsed = parse_trello_credentials(credential)
            data = await request(
                "GET",
                "https://api.trello.com/1/members/me",
                {
                    "Authorization": f'OAuth oauth_consumer_key="{parsed["api_key"]}", oauth_token="{parsed["token"]}"'
                },
                params={"fields": "id"},
            )
            return {"identity_id": str(data["id"])}
        if provider == "linear":
            data = await request(
                "POST",
                "https://api.linear.app/graphql",
                {"Authorization": credential},
                json={"query": "query { viewer { id } }"},
            )
            return {"identity_id": str(data["data"]["viewer"]["id"])}
        data = await request(
            "POST", "https://slack.com/api/auth.test", {"Authorization": f"Bearer {credential}"}
        )
        return {"identity_id": str(data["user_id"]), "workspace_id": str(data["team_id"])}

    async def read(self, task_id: UUID, provider: str, tool: str) -> dict[str, Any]:
        try:
            return await self._read(task_id, provider, tool)
        except httpx.HTTPError as exc:
            raise ConversationUnavailable(type(exc).__name__) from exc

    async def _read(self, task_id: UUID, provider: str, tool: str) -> dict[str, Any]:
        if tool not in {
            "READ_PR",
            "READ_DISCUSSION",
            "READ_REVIEWS",
            "READ_REVIEW_DELTA",
            "READ_CHECKS",
            "READ_TASK",
            "RECONCILE",
        }:
            raise ValueError("Unsupported semantic read")
        provider = (
            "github"
            if tool in {"READ_PR", "READ_REVIEWS", "READ_REVIEW_DELTA", "READ_CHECKS"}
            else provider
        )
        excerpt = 8000 if tool == "RECONCILE" else 1000
        if provider in {"dashboard", "engineering"}:
            return {"source": "local conversation already included"}
        root, headers, target = await self._target(task_id, provider)
        if provider == "github":
            if tool in {"READ_REVIEWS", "READ_REVIEW_DELTA", "READ_CHECKS"}:
                from app.platform.integrations.infrastructure.github_coordination import read_github

                return await read_github(self._request, root, headers, target, tool)
            if tool in {"READ_PR", "READ_TASK"}:
                data = await self._request("GET", f"{root}/pulls/{target['number']}", headers)
                return {
                    "title": data.get("title"),
                    "body": str(data.get("body") or "")[:6000],
                    "state": data.get("state"),
                    "head_sha": data["head"]["sha"],
                    "mergeable": data.get("mergeable"),
                    "merged": data.get("merged"),
                }
            issue = await self._request("GET", f"{root}/issues/{target['number']}", headers)
            page = max(1, (int(issue.get("comments") or 0) + 19) // 20)
            rows = await self._request(
                "GET",
                f"{root}/issues/{target['number']}/comments",
                headers,
                params={"per_page": 20, "page": page},
            )
            messages = [
                {
                    "id": str(row["id"]),
                    "text": str(row.get("body") or "")[:excerpt],
                    "actor": str((row.get("user") or {}).get("id", "")),
                    "created_at": row.get("created_at"),
                }
                for row in rows
            ]
        elif provider == "trello":
            if tool == "READ_TASK":
                data = await self._request(
                    "GET",
                    f"{root}/cards/{target['id']}",
                    headers,
                    params={"fields": "name,desc,idList,closed"},
                )
                return {
                    "title": data.get("name"),
                    "description": str(data.get("desc") or "")[:6000],
                    "state_id": data.get("idList"),
                    "closed": data.get("closed"),
                    "bounded_excerpt": True,
                }
            rows = await self._request(
                "GET",
                f"{root}/cards/{target['id']}/actions",
                headers,
                params={"filter": "commentCard", "limit": 20},
            )
            messages = [
                {
                    "id": str(row["id"]),
                    "text": str(row.get("data", {}).get("text") or "")[:excerpt],
                    "actor": str(row.get("idMemberCreator", "")),
                    "created_at": row.get("date"),
                }
                for row in rows
            ]
        elif provider == "slack":
            rows = await self._request(
                "GET", root + "/conversations.replies", headers, params={**target, "limit": 15}
            )
            messages = [
                {
                    "id": row["ts"],
                    "text": str(row.get("text") or "")[:excerpt],
                    "actor": str(row.get("user", "")),
                    "created_at": datetime.fromtimestamp(float(row["ts"]), UTC).isoformat(),
                }
                for row in rows.get("messages", [])
            ]
        else:
            if tool == "READ_TASK":
                data = await self._request(
                    "POST",
                    root,
                    headers,
                    json={
                        "query": "query($id: String!) { issue(id: $id) { title description state { name type } } }",
                        "variables": target,
                    },
                )
                issue = data["data"]["issue"]
                return {
                    "title": issue["title"],
                    "description": str(issue.get("description") or "")[:6000],
                    "state": issue["state"],
                    "bounded_excerpt": True,
                }
            rows = await self._request(
                "POST",
                root,
                headers,
                json={
                    "query": "query($id: String!) { issue(id: $id) { comments(last: 20) { nodes { id body createdAt user { id } } } } }",
                    "variables": target,
                },
            )
            messages = [
                {
                    "id": row["id"],
                    "text": str(row.get("body") or "")[:excerpt],
                    "actor": str((row.get("user") or {}).get("id", "")),
                    "created_at": row.get("createdAt"),
                }
                for row in rows["data"]["issue"]["comments"]["nodes"]
            ]
        return {"messages": messages, "bounded_excerpt": True}

    async def reply(self, task_id: UUID, provider: str, message: str, action_id: UUID) -> str:
        if provider in {"dashboard", "engineering"}:
            return f"dashboard:{action_id}"
        root, headers, target = await self._target(task_id, provider)
        if provider == "github":
            result = await self._request(
                "POST",
                f"{root}/issues/{target['number']}/comments",
                headers,
                json={"body": message},
            )
            return str(result["id"])
        if provider == "trello":
            result = await self._request(
                "POST",
                f"{root}/cards/{target['id']}/actions/comments",
                headers,
                json={"text": message},
            )
            return str(result["id"])
        if provider == "slack":
            result = await self._request(
                "POST",
                root + "/chat.postMessage",
                headers,
                json={
                    "channel": target["channel"],
                    "thread_ts": target["ts"],
                    "text": message,
                    "metadata": {
                        "event_type": "engineering_update",
                        "event_payload": {"action_id": str(action_id)},
                    },
                },
            )
            return str(result["ts"])
        result = await self._request(
            "POST",
            root,
            headers,
            json={
                "query": "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success comment { id } } }",
                "variables": {"input": {"issueId": target["id"], "body": message}},
            },
        )
        if not result["data"]["commentCreate"]["success"]:
            raise ValueError("Linear did not confirm comment creation")
        return str(result["data"]["commentCreate"]["comment"]["id"])
