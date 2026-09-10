from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.engineering.infrastructure.models import TaskPhaseRun
from app.engineering.infrastructure.task_models import Task
from app.teams.application.profiles import ProfileConflict, ProfileView
from app.teams.domain.profiles import AgentProfile, RoleKind
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


async def initialize_profiles(
    session: AsyncSession, team_id: UUID, profiles: tuple[AgentProfile, ...]
) -> None:
    """Seed missing fixed roles in the caller's Team-locked transaction.

    Never overwrite a configured profile, and never commit half of Team setup.
    """
    existing = set(
        await session.scalars(
            select(TeamAgentProfile.role_kind).where(TeamAgentProfile.team_id == team_id)
        )
    )
    for profile in profiles:
        if profile.role_kind not in existing:
            session.add(TeamAgentProfile(team_id=team_id, **asdict(profile)))
    await session.flush()


def view(row: TeamAgentProfile) -> ProfileView:
    fields = {key: getattr(row, key) for key in AgentProfile.__dataclass_fields__}
    fields["role_kind"] = RoleKind(row.role_kind)
    return ProfileView(row.id, row.team_id, row.version, AgentProfile(**fields))


class SqlTeamProfiles:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _team(self, team_id: UUID, *, lock: bool = False) -> Team:
        query = select(Team).where(Team.id == team_id, Team.archived_at.is_(None))
        if lock:
            query = query.with_for_update()
        team = await self.session.scalar(query)
        if team is None:
            raise LookupError("Team not found")
        return team

    async def list_profiles(self, team_id: UUID) -> list[ProfileView]:
        await self._team(team_id)
        return await self._profile_views(team_id)

    async def _profile_views(self, team_id: UUID) -> list[ProfileView]:
        rows = await self.session.scalars(
            select(TeamAgentProfile).where(TeamAgentProfile.team_id == team_id)
        )
        order = {role.value: i for i, role in enumerate(RoleKind)}
        return [view(row) for row in sorted(rows, key=lambda row: order[row.role_kind])]

    async def initialize(
        self, team_id: UUID, profiles: tuple[AgentProfile, ...]
    ) -> list[ProfileView]:
        await self._team(team_id, lock=True)
        await initialize_profiles(self.session, team_id, profiles)
        result = await self._profile_views(team_id)
        await self.session.commit()
        return result

    async def save(
        self, team_id: UUID, role: RoleKind, profile: AgentProfile, version: int
    ) -> ProfileView:
        await self._team(team_id, lock=True)
        row = await self.session.scalar(
            select(TeamAgentProfile)
            .where(
                TeamAgentProfile.team_id == team_id,
                TeamAgentProfile.role_kind == role.value,
            )
            .with_for_update()
        )
        if row is None:
            raise LookupError("Initialize the team's fixed profiles first")
        if row.version != version:
            raise ProfileConflict("Profile changed; reload before saving")
        for key, value in asdict(profile).items():
            setattr(row, key, value)
        row.version += 1
        await self.session.flush()
        result = view(row)
        await self.session.commit()
        return result

    async def activity(self, team_id: UUID) -> dict[str, Any]:
        team = await self._team(team_id)
        rows = list(
            await self.session.scalars(
                select(Task)
                .options(
                    load_only(
                        Task.title,
                        Task.priority,
                        Task.status,
                        Task.stage,
                        Task.wait_reason,
                        Task.requirement_version,
                        Task.pull_request_url,
                        raiseload=True,
                    )
                )
                .where(
                    Task.team_id == team_id,
                    Task.archived_at.is_(None),
                    Task.status.not_in(["MERGED", "CANCELLED", "FAILED"]),
                )
                .order_by(Task.priority, Task.created_at)
                .limit(100)
            )
        )
        phases = list(
            await self.session.scalars(
                select(TaskPhaseRun)
                .join(Task)
                .where(
                    Task.team_id == team_id,
                )
                .order_by(TaskPhaseRun.started_at.desc())
                .limit(40)
            )
        )
        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "enabled": team.enabled,
            "tasks": [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "priority": task.priority,
                    "status": task.status,
                    "stage": task.stage,
                    "wait_reason": task.wait_reason,
                    "requirement_version": task.requirement_version,
                    "pull_request_url": task.pull_request_url,
                }
                for task in rows
            ],
            "milestones": [
                {
                    "id": str(phase.id),
                    "task_id": str(phase.task_id),
                    "stage": phase.stage,
                    "status": phase.status,
                    "actor": phase.actor,
                    "started_at": phase.started_at.isoformat(),
                    "finished_at": phase.finished_at.isoformat() if phase.finished_at else None,
                }
                for phase in phases
            ],
        }
