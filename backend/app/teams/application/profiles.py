from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.teams.domain.profiles import AgentProfile, RoleKind, default_profiles


@dataclass(frozen=True)
class ProfileView:
    id: UUID
    team_id: UUID
    version: int
    profile: AgentProfile


class ProfileConflict(ValueError):
    pass


class TeamProfiles(Protocol):
    async def list_profiles(self, team_id: UUID) -> list[ProfileView]: ...
    async def initialize(
        self, team_id: UUID, profiles: tuple[AgentProfile, ...]
    ) -> list[ProfileView]: ...
    async def save(
        self, team_id: UUID, role: RoleKind, profile: AgentProfile, version: int
    ) -> ProfileView: ...
    async def activity(self, team_id: UUID) -> dict[str, Any]: ...


class ManageProfiles:
    def __init__(self, store: TeamProfiles) -> None:
        self.store = store

    async def initialize(self, team_id: UUID) -> list[ProfileView]:
        return await self.store.initialize(team_id, default_profiles())

    async def save(
        self, team_id: UUID, role: RoleKind, profile: AgentProfile, version: int
    ) -> ProfileView:
        if profile.role_kind != role:
            raise ValueError("A fixed role cannot be replaced with another role")
        return await self.store.save(team_id, role, profile, version)
