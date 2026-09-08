from dataclasses import dataclass
from typing import Protocol


class IntegrationNotConfigured(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RepositoryDiscoveryView:
    external_repo_id: str
    owner: str
    name: str
    full_name: str
    clone_url: str
    default_branch: str
    private: bool


@dataclass(frozen=True, slots=True)
class WorkflowStateView:
    id: str
    name: str
    type: str
    team_id: str
    team_name: str
    team_key: str


@dataclass(frozen=True, slots=True)
class LinearMemberView:
    id: str
    name: str
    email: str
    active: bool


@dataclass(frozen=True, slots=True)
class TrelloBoardView:
    id: str
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class TrelloListView:
    id: str
    name: str
    closed: bool


class IntegrationDiscoveryWorkflow(Protocol):
    async def github_repositories(self) -> list[RepositoryDiscoveryView]: ...
    async def linear_workflow_states(self) -> list[WorkflowStateView]: ...
    async def linear_members(self) -> list[LinearMemberView]: ...
    async def trello_boards(self) -> list[TrelloBoardView]: ...
    async def trello_lists(self, board_id: str) -> list[TrelloListView]: ...
