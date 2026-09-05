import builtins
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, String, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.task_queries import ExternalTaskView, TaskListFilters, TaskView
from app.db.models import ExternalTaskSnapshot, Repository, Task, Team
from app.infrastructure.persistence.repositories import task_to_domain


class SqlAlchemyTaskQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, limit: int, filters: TaskListFilters) -> list[TaskView]:
        statement: Select[tuple[Task]] = select(Task)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            statement = statement.where(
                or_(Task.title.ilike(pattern), Task.external_key.ilike(pattern))
            )
        if filters.states:
            statement = statement.where(Task.state.in_(filters.states))
        if filters.repository_id:
            statement = statement.where(Task.repository_id == filters.repository_id)
        if filters.priorities:
            statement = statement.where(Task.priority.in_(filters.priorities))
        if filters.created_from:
            statement = statement.where(Task.created_at >= filters.created_from)
        if filters.created_to:
            statement = statement.where(Task.created_at <= filters.created_to)
        if filters.due_from:
            statement = statement.where(Task.due_at >= filters.due_from)
        if filters.due_to:
            statement = statement.where(Task.due_at <= filters.due_to)
        if filters.updated_from:
            statement = statement.where(Task.updated_at >= filters.updated_from)
        if filters.updated_to:
            statement = statement.where(Task.updated_at <= filters.updated_to)
        if filters.assigned_team_id:
            statement = statement.where(Task.team_id == filters.assigned_team_id)
        elif filters.unassigned:
            statement = statement.where(Task.team_id.is_(None))
        snapshot_filters = []
        if filters.provider == "internal":
            statement = statement.where(~exists().where(ExternalTaskSnapshot.task_id == Task.id))
        elif filters.provider:
            snapshot_filters.append(ExternalTaskSnapshot.provider == filters.provider)
        if filters.assignee:
            pattern = f"%{filters.assignee.strip()}%"
            snapshot_filters.append(
                or_(
                    ExternalTaskSnapshot.assignee_id == filters.assignee,
                    ExternalTaskSnapshot.raw_payload["assignee"]["name"].as_string().ilike(pattern),
                    ExternalTaskSnapshot.raw_payload["assignee"]["email"]
                    .as_string()
                    .ilike(pattern),
                )
            )
        for key, value in (("team", filters.team), ("project", filters.project)):
            if value:
                if key == "project":
                    statement = statement.where(
                        or_(
                            Task.project_name.ilike(f"%{value.strip()}%"),
                            exists().where(
                                ExternalTaskSnapshot.task_id == Task.id,
                                ExternalTaskSnapshot.raw_payload[key]["name"]
                                .as_string()
                                .ilike(f"%{value.strip()}%"),
                            ),
                        )
                    )
                    continue
                snapshot_filters.append(
                    ExternalTaskSnapshot.raw_payload[key]["name"]
                    .as_string()
                    .ilike(f"%{value.strip()}%")
                )
        if filters.provider_state:
            snapshot_filters.append(
                or_(
                    ExternalTaskSnapshot.state_id == filters.provider_state,
                    ExternalTaskSnapshot.raw_payload["state"]["name"]
                    .as_string()
                    .ilike(f"%{filters.provider_state.strip()}%"),
                )
            )
        if filters.label:
            label = filters.label.strip().lower()
            statement = statement.where(
                or_(
                    func.lower(Task.labels.cast(String)).contains(label),
                    exists().where(
                        ExternalTaskSnapshot.task_id == Task.id,
                        func.lower(ExternalTaskSnapshot.raw_payload.cast(String)).contains(label),
                    ),
                )
            )
        if snapshot_filters:
            statement = statement.where(
                exists().where(
                    ExternalTaskSnapshot.task_id == Task.id,
                    *snapshot_filters,
                )
            )
        sort_columns = {
            "priority": Task.priority,
            "created": Task.created_at,
            "updated": Task.updated_at,
            "due": Task.due_at,
        }
        sort_column = sort_columns[filters.sort]
        ordering = (
            sort_column.desc().nullslast()
            if filters.direction == "desc"
            else sort_column.asc().nullslast()
        )
        records = list(
            (
                await self._session.scalars(
                    statement.order_by(ordering, Task.created_at.desc()).limit(limit)
                )
            ).all()
        )
        return await self._views(records)

    async def get(self, task_id: uuid.UUID) -> TaskView | None:
        record = await self._session.get(Task, task_id)
        return (await self._views([record]))[0] if record is not None else None

    async def _views(self, records: Sequence[Task]) -> builtins.list[TaskView]:
        if not records:
            return []
        task_ids = [record.id for record in records]
        snapshots = list(
            (
                await self._session.scalars(
                    select(ExternalTaskSnapshot)
                    .where(ExternalTaskSnapshot.task_id.in_(task_ids))
                    .order_by(ExternalTaskSnapshot.synchronized_at.asc())
                )
            ).all()
        )
        latest = {snapshot.task_id: snapshot for snapshot in snapshots}
        repository_ids = {record.repository_id for record in records if record.repository_id}
        repositories = (
            {
                repository.id: repository
                for repository in (
                    await self._session.scalars(
                        select(Repository).where(Repository.id.in_(repository_ids))
                    )
                ).all()
            }
            if repository_ids
            else {}
        )
        team_ids = {record.team_id for record in records if record.team_id}
        teams = (
            {
                team.id: team
                for team in (
                    await self._session.scalars(select(Team).where(Team.id.in_(team_ids)))
                ).all()
            }
            if team_ids
            else {}
        )
        return [
            TaskView(
                task_to_domain(record),
                self._external(latest.get(record.id)),
                (
                    f"{repositories[record.repository_id].owner}/{repositories[record.repository_id].name}"
                    if record.repository_id in repositories
                    else None
                ),
                record.due_at,
                record.started_at,
                record.completed_at,
                record.team_id,
                teams[record.team_id].name if record.team_id in teams else None,
                record.project_name,
                tuple(record.labels or []),
                float(record.estimate) if record.estimate is not None else None,
            )
            for record in records
        ]

    @staticmethod
    def _external(snapshot: ExternalTaskSnapshot | None) -> ExternalTaskView | None:
        if snapshot is None:
            return None
        raw: dict[str, Any] = snapshot.raw_payload or {}
        assignee = raw.get("assignee") or {}
        creator = raw.get("creator") or {}
        state = raw.get("state") or {}
        team = raw.get("team") or {}
        project = raw.get("project") or {}
        labels_value = raw.get("labels") or []
        labels = labels_value.get("nodes", []) if isinstance(labels_value, dict) else labels_value
        estimate = raw.get("estimate")
        return ExternalTaskView(
            snapshot.provider,
            snapshot.external_id,
            snapshot.identifier,
            str(raw["url"]) if raw.get("url") else None,
            snapshot.state_id,
            str(state["name"]) if state.get("name") else None,
            snapshot.assignee_id,
            str(assignee["name"]) if assignee.get("name") else None,
            str(assignee["email"]) if assignee.get("email") else None,
            str(creator["name"]) if creator.get("name") else None,
            str(team["name"]) if team.get("name") else None,
            str(team["key"]) if team.get("key") else None,
            str(project["name"]) if project.get("name") else None,
            tuple(str(label.get("name")) for label in labels if label.get("name")),
            float(estimate) if isinstance(estimate, (int, float)) else None,
            str(raw["dueDate"]) if raw.get("dueDate") else None,
            str(raw["createdAt"]) if raw.get("createdAt") else None,
            str(raw["updatedAt"]) if raw.get("updatedAt") else None,
            raw,
        )
