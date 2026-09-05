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

    async def _graphql(self, query: str, variables: dict[str, str] | None = None) -> dict[str, Any]:
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

    async def update_issue_state(self, issue_id: str, state_id: str) -> None:
        query = """
        mutation UpdateIssueState($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: {stateId: $stateId}) { success }
        }
        """
        data = await self._graphql(query, {"id": issue_id, "stateId": state_id})
        if not data.get("issueUpdate", {}).get("success"):
            raise RuntimeError("Linear did not confirm the issue state update")
