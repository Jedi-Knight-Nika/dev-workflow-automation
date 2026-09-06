import hashlib
import hmac
import time
from typing import Any, TypedDict

from app.integrations.http import integration_http_pool


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
        response = await integration_http_pool.request(
            "POST",
            "https://api.linear.app/graphql",
            headers=self.headers,
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

    async def _connection_nodes(
        self,
        query: str,
        connection_name: str,
        variables: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Read a complete Linear GraphQL connection using its opaque cursor."""
        nodes: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page_variables = dict(variables or {})
            page_variables["after"] = cursor
            data = await self._graphql(query, page_variables)
            connection = data.get(connection_name)
            if not isinstance(connection, dict):
                raise TypeError(f"Linear returned an invalid {connection_name} connection")
            batch = connection.get("nodes", [])
            if not isinstance(batch, list):
                raise TypeError(f"Linear returned invalid {connection_name} nodes")
            nodes.extend(node for node in batch if isinstance(node, dict))
            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return nodes
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                raise RuntimeError(
                    f"Linear {connection_name} pagination returned an invalid cursor"
                )
            cursor = next_cursor

    async def list_workflow_states(self) -> list[LinearWorkflowState]:
        query = """
        query WorkflowStates($after: String) {
          workflowStates(first: 250, after: $after) {
            nodes { id name type team { id name key } }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        nodes = await self._connection_nodes(query, "workflowStates")
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
        nodes = await self._connection_nodes(
            """
            query Members($after: String) {
              users(first: 250, after: $after) {
                nodes { id name email active }
                pageInfo { hasNextPage endCursor }
              }
            }
            """,
            "users",
        )
        return sorted(
            [
                {
                    "id": str(node["id"]),
                    "name": str(node.get("name") or node.get("email") or "Unknown"),
                    "email": str(node.get("email") or ""),
                    "active": bool(node.get("active", True)),
                }
                for node in nodes
            ],
            key=lambda member: member["name"].lower(),
        )

    async def list_issues(self, assignee_id: str, state_ids: list[str]) -> list[LinearIssue]:
        nodes = await self._connection_nodes(
            """
            query AssignedIssues($assigneeId: ID!, $stateIds: [ID!]!, $after: String) {
              issues(first: 100, after: $after, filter: {
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
                pageInfo { hasNextPage endCursor }
              }
            }
            """,
            "issues",
            {"assigneeId": assignee_id, "stateIds": state_ids},
        )
        issues: list[LinearIssue] = []
        for node in nodes:
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
