import hashlib
import hmac
import time
from typing import Any, TypedDict

import httpx


class LinearWorkflowState(TypedDict):
    id: str
    name: str
    type: str
    team_id: str
    team_name: str
    team_key: str


class LinearMember(TypedDict):
    id: str
    name: str
    email: str
    active: bool


class LinearIssue(TypedDict):
    id: str
    identifier: str
    title: str
    description: str
    priority: int
    assignee_id: str | None
    state_id: str | None
    raw: dict[str, Any]


def verify_linear_signature(
    body: bytes,
    secret: str,
    signature: str | None,
    webhook_timestamp_ms: int | None,
    tolerance_seconds: int = 60,
) -> bool:
    if not secret or not signature or webhook_timestamp_ms is None:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    age_ms = abs(round(time.time() * 1000) - webhook_timestamp_ms)
    return age_ms <= tolerance_seconds * 1000


class LinearClient:
    def __init__(self, api_key: str) -> None:
        self.headers = {"authorization": api_key, "content-type": "application/json"}

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.post(
                "https://api.linear.app/graphql",
                json={"query": query, "variables": variables or {}},
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        if body.get("errors"):
            message = str(body["errors"][0].get("message", "Unknown GraphQL error"))
            raise RuntimeError(f"Linear GraphQL error: {message}")
        data = body.get("data")
        if not isinstance(data, dict):
            raise TypeError("Linear returned an invalid GraphQL response")
        return data

    async def list_workflow_states(self) -> list[LinearWorkflowState]:
        query = """
        query WorkflowStates {
          workflowStates(first: 250) {
            nodes { id name type team { id name key } }
          }
        }
        """
        data = await self._graphql(query)
        nodes = data.get("workflowStates", {}).get("nodes", [])
        states: list[LinearWorkflowState] = []
        for node in nodes:
            team = node.get("team") or {}
            states.append(
                {
                    "id": str(node["id"]),
                    "name": str(node["name"]),
                    "type": str(node.get("type", "")),
                    "team_id": str(team.get("id", "")),
                    "team_name": str(team.get("name", "")),
                    "team_key": str(team.get("key", "")),
                }
            )
        return sorted(states, key=lambda state: (state["team_name"], state["name"]))

    async def list_members(self) -> list[LinearMember]:
        data = await self._graphql(
            """query Members { users(first: 250) { nodes { id name email active } } }"""
        )
        return sorted(
            [
                {
                    "id": str(node["id"]),
                    "name": str(node.get("name") or node.get("email") or "Unknown"),
                    "email": str(node.get("email") or ""),
                    "active": bool(node.get("active", True)),
                }
                for node in data.get("users", {}).get("nodes", [])
            ],
            key=lambda member: member["name"].lower(),
        )

    async def list_issues(self, assignee_id: str, state_ids: list[str]) -> list[LinearIssue]:
        data = await self._graphql(
            """
            query AssignedIssues($assigneeId: ID!, $stateIds: [ID!]!) {
              issues(first: 100, filter: {
                assignee: { id: { eq: $assigneeId } },
                state: { id: { in: $stateIds } }
              }) {
                nodes {
                  id identifier title description priority url dueDate estimate
                  createdAt updatedAt completedAt startedAt
                  assignee { id name email }
                  creator { id name email }
                  state { id name type }
                  team { id name key }
                  project { id name }
                  labels { nodes { id name color } }
                }
              }
            }
            """,
            {"assigneeId": assignee_id, "stateIds": state_ids},
        )
        issues: list[LinearIssue] = []
        for node in data.get("issues", {}).get("nodes", []):
            assignee = node.get("assignee") or {}
            state = node.get("state") or {}
            issues.append(
                {
                    "id": str(node["id"]),
                    "identifier": str(node["identifier"]),
                    "title": str(node.get("title") or node["identifier"]),
                    "description": str(node.get("description") or ""),
                    "priority": int(node.get("priority") or 0),
                    "assignee_id": str(assignee["id"]) if assignee.get("id") else None,
                    "state_id": str(state["id"]) if state.get("id") else None,
                    "raw": dict(node),
                }
            )
        return issues

    async def update_issue_state(self, issue_id: str, state_id: str) -> None:
        query = """
        mutation UpdateIssueState($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: {stateId: $stateId}) { success }
        }
        """
        data = await self._graphql(query, {"id": issue_id, "stateId": state_id})
        if not data.get("issueUpdate", {}).get("success"):
            raise RuntimeError("Linear did not confirm the issue state update")
