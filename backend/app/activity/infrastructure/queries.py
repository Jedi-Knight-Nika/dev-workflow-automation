from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only
from sqlalchemy.sql.elements import ColumnElement

from app.activity.application.ports import ActivityScope, ActivityWindow
from app.activity.infrastructure.capacity import capacity_evidence
from app.activity.infrastructure.models import (
    ActivityEvent,
    ActivityFileChange,
    ActivityProjectionState,
)
from app.activity.infrastructure.monitoring import activity_monitoring
from app.activity.infrastructure.relationships import inspect_related, parents_for
from app.engineering.infrastructure.task_models import Task, TaskRepositoryScope
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.team_models import Team

TASK_METADATA = load_only(
    Task.id, Task.title, Task.external_key, Task.team_id, Task.project_name, raiseload=True
)


def window_filter(window: ActivityWindow) -> ColumnElement[bool]:
    return and_(
        ActivityEvent.occurred_at >= window.start,
        ActivityEvent.occurred_at <= window.end,
        ActivityEvent.detail_level <= window.detail,
    )


def projection_status(state: ActivityProjectionState | None) -> dict[str, Any]:
    activity_monitoring.lag.set(
        (datetime.now(UTC) - state.last_success_at).total_seconds()
        if state and state.last_success_at
        else -1
    )
    delayed = (
        state is None
        or state.last_success_at is None
        or (datetime.now(UTC) - state.last_success_at).total_seconds() > 30
        or not state.caught_up
    )
    return {
        "delayed": delayed,
        "last_projected_at": state.last_success_at if state else None,
        "warnings": ["Activity history is catching up or the projector is unavailable."]
        if delayed
        else [],
    }


class SqlActivityQueries:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        max_events: int,
        max_tasks: int,
        max_files: int = 5000,
        collect_files: bool = True,
    ):
        self.sessions, self.max_events, self.max_tasks = sessions, max_events, max_tasks
        self.max_files = max_files
        self.collect_files = collect_files

    @asynccontextmanager
    async def read(self, operation: str = "query") -> AsyncIterator[AsyncSession]:
        with activity_monitoring.query(operation):
            async with self.sessions() as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                yield session

    async def scope_filter(
        self, session: AsyncSession, scope: ActivityScope
    ) -> ColumnElement[bool]:
        if scope.kind == "workspace" and scope.id is None:
            return Task.id.is_not(None)
        if scope.kind == "project" and scope.id:
            if not await session.scalar(
                select(Task.id).where(Task.project_name == scope.id).limit(1)
            ):
                raise LookupError("Project group not found")
            return Task.project_name == scope.id
        columns = {"team": Team.id, "task": Task.id, "repository": Repository.id}
        if scope.kind not in columns or not scope.id:
            raise ValueError("Choose a valid activity scope")
        try:
            identity = UUID(scope.id)
        except ValueError as exc:
            raise ValueError("Invalid activity scope ID") from exc
        column = columns[scope.kind]
        if await session.scalar(select(column).where(column == identity)) is None:
            raise LookupError("Activity scope not found")
        if scope.kind == "task":
            return Task.id == identity
        if scope.kind == "team":
            return Task.team_id == identity
        return and_(
            or_(
                Task.repository_id == identity,
                Task.id.in_(
                    select(TaskRepositoryScope.task_id).where(
                        TaskRepositoryScope.repository_id == identity
                    )
                ),
            ),
            or_(
                ActivityEvent.kind.not_in(["CODE_CHANGED", "DEPLOYMENT_STATUS_CHANGED"]),
                ActivityEvent.payload["repository_id"].astext == str(identity),
            ),
        )

    async def preflight(self, window: ActivityWindow) -> dict[str, Any]:
        async with self.read("preflight") as session:
            scope = await self.scope_filter(session, window.scope)
            through = int(await session.scalar(select(func.max(ActivityEvent.sequence))) or 0)
            bounded = (
                select(ActivityEvent.sequence, ActivityEvent.task_id)
                .join(Task)
                .where(
                    scope,
                    window_filter(window),
                    ActivityEvent.sequence <= through,
                )
                .limit(self.max_events + 1)
                .subquery()
            )
            count, tasks = (
                await session.execute(
                    select(func.count(), func.count(func.distinct(bounded.c.task_id))).select_from(
                        bounded
                    )
                )
            ).one()
            file_sample = (
                select(ActivityFileChange.id)
                .where(ActivityFileChange.event_sequence.in_(select(bounded.c.sequence)))
                .limit(self.max_files + 1)
                .subquery()
            )
            file_count = int(
                await session.scalar(select(func.count()).select_from(file_sample)) or 0
            )
            state = await session.get(ActivityProjectionState, 1)
            coverage = await self.file_coverage(session, window, scope, through)
            capacity = {"teams": [], "truncated": True}
            if count <= self.max_events and tasks <= self.max_tasks:
                capacity = await self._capacity(session, window, scope, through)
            return {
                "scope": {"type": window.scope.kind, "id": window.scope.id},
                "from": window.start,
                "to": window.end,
                "through_sequence": through,
                "estimated_events": count,
                "tasks": tasks,
                "max_events": self.max_events,
                "max_files": self.max_files,
                "file_changes": file_count,
                "max_tasks": self.max_tasks,
                "too_large": count > self.max_events
                or tasks > self.max_tasks
                or file_count > self.max_files,
                "live_available": True,
                **projection_status(state),
                "file_history": coverage,
                "capacity": capacity,
            }

    async def capacity(self, window: ActivityWindow, through: int) -> dict[str, Any]:
        async with self.read("capacity") as session:
            scope = await self.scope_filter(session, window.scope)
            return await self._capacity(session, window, scope, through)

    async def _capacity(
        self,
        session: AsyncSession,
        window: ActivityWindow,
        scope: ColumnElement[bool],
        through: int,
    ) -> dict[str, Any]:
        if window.scope.kind == "team":
            team_ids = [UUID(str(window.scope.id))]
        elif window.scope.kind == "task":
            team_ids = list(
                await session.scalars(select(Task.team_id).where(scope, Task.team_id.is_not(None)))
            )
        else:
            team_ids = list(
                await session.scalars(
                    select(Task.team_id)
                    .join(ActivityEvent)
                    .where(
                        scope,
                        window_filter(window),
                        ActivityEvent.sequence <= through,
                        Task.team_id.is_not(None),
                    )
                    .distinct()
                    .order_by(Task.team_id)
                    .limit(self.max_tasks + 1)
                )
            )
        evidence = await capacity_evidence(
            session,
            window,
            [id for id in team_ids[: self.max_tasks] if id is not None],
            through,
            self.max_events,
        )
        evidence["truncated"] |= len(team_ids) > self.max_tasks
        return evidence

    async def projection_status(self) -> dict[str, Any]:
        async with self.read() as session:
            return projection_status(await session.get(ActivityProjectionState, 1))

    async def aggregate(self, window: ActivityWindow, through: int) -> dict[str, Any]:
        # At most 169 hourly or 366 daily buckets, independent of raw event count.
        unit = "hour" if window.end - window.start <= timedelta(days=7) else "day"
        async with self.read("aggregate") as session:
            scope = await self.scope_filter(session, window.scope)
            bucket = func.date_trunc(unit, ActivityEvent.occurred_at, "UTC")
            rows = await session.execute(
                select(
                    bucket.label("at"),
                    func.count().label("events"),
                    func.count(func.distinct(ActivityEvent.task_id)).label("tasks"),
                    func.count()
                    .filter(ActivityEvent.kind == "VALIDATION_PASSED")
                    .label("validation_passed"),
                    func.count()
                    .filter(ActivityEvent.kind == "VALIDATION_FAILED")
                    .label("validation_failed"),
                    func.count().filter(ActivityEvent.kind == "REVIEW_RECEIVED").label("reviews"),
                    func.count()
                    .filter(ActivityEvent.kind == "HUMAN_RESPONDED")
                    .label("human_responses"),
                )
                .join(Task)
                .where(scope, window_filter(window), ActivityEvent.sequence <= through)
                .group_by(bucket)
                .order_by(bucket)
                .limit(367)
            )
            buckets = [dict(row._mapping) for row in rows]
            return {
                "unit": unit,
                "buckets": buckets,
                "events": sum(row["events"] for row in buckets),
                "through_sequence": through,
            }

    async def events(
        self, window: ActivityWindow, after: int, through: int | None, limit: int
    ) -> dict[str, Any]:
        async with self.read("events") as session:
            scope = await self.scope_filter(session, window.scope)
            through = (
                through
                if through is not None
                else int(await session.scalar(select(func.max(ActivityEvent.sequence))) or 0)
            )
            query = (
                select(ActivityEvent, Task, Team.name)
                .options(TASK_METADATA)
                .select_from(ActivityEvent)
                .join(Task, Task.id == ActivityEvent.task_id)
                .outerjoin(Team, Task.team_id == Team.id)
                .where(
                    scope,
                    ActivityEvent.sequence > after,
                    window_filter(window),
                    ActivityEvent.sequence <= through,
                )
            )
            rows = (
                await session.execute(query.order_by(ActivityEvent.sequence).limit(limit + 1))
            ).all()
            visible = rows[:limit]
            activity_monitoring.returned.inc(len(visible))
            if not visible:
                return {"events": [], "next_sequence": max(after, through), "has_more": False}
            parents = await parents_for(session, [event for event, _, _ in visible], through)
            file_rows = await session.scalars(
                select(ActivityFileChange)
                .where(
                    ActivityFileChange.event_sequence.in_(
                        [event.sequence for event, _, _ in visible]
                    )
                )
                .order_by(ActivityFileChange.path)
                .limit(self.max_files + 1)
            )
            files: dict[int, list[dict[str, Any]]] = {}
            for file_number, item in enumerate(file_rows):
                if file_number >= self.max_files:
                    raise ValueError("Choose a smaller range for file activity")
                if window.scope.kind == "repository" and str(item.repository_id) != window.scope.id:
                    continue
                files.setdefault(item.event_sequence, []).append(
                    {
                        "repository_id": str(item.repository_id),
                        "operation": item.operation,
                        "path": item.path,
                        "previous_path": item.previous_path,
                        "lines_added": item.lines_added,
                        "lines_deleted": item.lines_deleted,
                    }
                )
            events = [
                {
                    "sequence": event.sequence,
                    "id": str(event.id),
                    "kind": event.kind,
                    "occurred_at": event.occurred_at,
                    "recorded_at": event.recorded_at,
                    "task_id": str(task.id),
                    "task_title": task.title[:180],
                    "task_key": task.external_key,
                    "team_id": str(task.team_id) if task.team_id else None,
                    "team_name": name,
                    "project": task.project_name,
                    "actor_type": event.actor_type,
                    "actor": event.actor,
                    "correlation_id": str(event.correlation_id) if event.correlation_id else None,
                    "payload": event.payload,
                    "files": files.get(event.sequence, []),
                    "parents": parents.get(event.sequence, []),
                    "unresolved_parents": max(
                        0, len(event.references) - len(parents.get(event.sequence, []))
                    ),
                    "file_status": event.file_status,
                }
                for event, task, name in visible
            ]
            return {
                "events": events,
                "next_sequence": events[-1]["sequence"]
                if len(rows) > limit
                else max(after, through),
                "has_more": len(rows) > limit,
            }

    async def file_coverage(
        self,
        session: AsyncSession,
        window: ActivityWindow,
        scope: ColumnElement[bool],
        through: int,
    ) -> dict[str, Any]:
        sample = (
            select(ActivityEvent.file_status)
            .join(Task)
            .where(
                scope,
                window_filter(window),
                ActivityEvent.sequence <= through,
                ActivityEvent.kind == "VALIDATION_PASSED",
            )
            .limit(self.max_events + 1)
            .subquery()
        )
        rows = await session.execute(
            select(func.coalesce(sample.c.file_status, "PENDING"), func.count()).group_by(
                sample.c.file_status
            )
        )
        counts = dict(rows.all())
        return {
            "counts": counts,
            "incomplete": any(status != "COMPLETE" for status in counts),
            "sampled": sum(counts.values()) > self.max_events,
            "collection_enabled": self.collect_files,
        }

    async def coverage(self, window: ActivityWindow) -> dict[str, Any]:
        async with self.read() as session:
            scope = await self.scope_filter(session, window.scope)
            through = int(await session.scalar(select(func.max(ActivityEvent.sequence))) or 0)
            return await self.file_coverage(session, window, scope, through)

    async def inspect(self, window: ActivityWindow, sequence: int, through: int) -> dict[str, Any]:
        page = await self.events(window, sequence - 1, min(sequence, through), 1)
        if not page["events"] or page["events"][0]["sequence"] != sequence:
            raise LookupError("Activity event not found in this view")
        async with self.read() as session:
            event = await session.get(ActivityEvent, sequence)
            if event is None:
                raise LookupError("Activity event no longer exists")
            # Related source records may fall outside the time window, but must belong to this task.
            event_dto = page["events"][0]
            event_dto["parents"] = (await parents_for(session, [event], through)).get(sequence, [])
            event_dto["unresolved_parents"] = max(
                0, len(event.references) - len(event_dto["parents"])
            )
            return {"event": event_dto, **await inspect_related(session, event, through)}

    async def baseline(self, window: ActivityWindow, through: int) -> dict[str, Any]:
        async with self.read() as session:
            scope = await self.scope_filter(session, window.scope)
            active_ids = (
                select(ActivityEvent.task_id)
                .join(Task)
                .where(
                    scope,
                    window_filter(window),
                    ActivityEvent.sequence <= through,
                )
                .distinct()
                .order_by(ActivityEvent.task_id)
                .limit(self.max_tasks + 1)
            )
            ids = list(await session.scalars(active_ids))
            if len(ids) > self.max_tasks:
                raise ValueError("Choose a smaller time range or activity scope")
            if not ids:
                return {"tasks": []}
            latest = (
                select(ActivityEvent.task_id, ActivityEvent.payload)
                .where(
                    ActivityEvent.task_id.in_(ids),
                    ActivityEvent.kind == "TASK_STATE_CHANGED",
                    ActivityEvent.occurred_at < window.start,
                    ActivityEvent.sequence <= through,
                )
                .distinct(ActivityEvent.task_id)
                .order_by(
                    ActivityEvent.task_id,
                    ActivityEvent.occurred_at.desc(),
                    ActivityEvent.sequence.desc(),
                )
            )
            states = {task_id: payload for task_id, payload in await session.execute(latest)}
            dependency_rows = (
                await session.execute(
                    select(ActivityEvent.task_id, ActivityEvent.payload)
                    .where(
                        ActivityEvent.task_id.in_(ids),
                        ActivityEvent.kind == "TASK_DEPENDENCIES_CHANGED",
                        ActivityEvent.occurred_at < window.start,
                        ActivityEvent.sequence <= through,
                    )
                    .distinct(ActivityEvent.task_id)
                    .order_by(
                        ActivityEvent.task_id,
                        ActivityEvent.occurred_at.desc(),
                        ActivityEvent.sequence.desc(),
                    )
                )
            ).all()
            dependencies = {task_id: payload for task_id, payload in dependency_rows}
            rows = await session.execute(
                select(Task, Team.name)
                .options(TASK_METADATA)
                .outerjoin(Team, Team.id == Task.team_id)
                .where(Task.id.in_(ids))
            )
            return {
                "tasks": [
                    {
                        "id": str(task.id),
                        "title": task.title[:180],
                        "key": task.external_key,
                        "team_id": str(task.team_id) if task.team_id else None,
                        "team_name": name,
                        "project": task.project_name,
                        "status": states.get(task.id, {}).get("to_status", "UNKNOWN"),
                        "stage": states.get(task.id, {}).get("to_stage", "UNKNOWN"),
                        "wait_reason": states.get(task.id, {}).get("wait_reason", "NONE"),
                        "version": states.get(task.id, {}).get("version", 0),
                        "dependency_ids": dependencies.get(task.id, {}).get("dependency_ids", []),
                    }
                    for task, name in rows
                ]
            }

    async def choices(self) -> dict[str, Any]:
        async with self.read() as session:
            teams = (
                await session.execute(select(Team.id, Team.name).order_by(Team.name).limit(201))
            ).all()
            repositories = (
                await session.execute(
                    select(Repository.id, Repository.owner, Repository.name)
                    .order_by(Repository.owner, Repository.name)
                    .limit(201)
                )
            ).all()
            projects = list(
                await session.scalars(
                    select(Task.project_name)
                    .where(and_(Task.project_name.is_not(None), Task.project_name != ""))
                    .distinct()
                    .order_by(Task.project_name)
                    .limit(201)
                )
            )
            return {
                "teams": [{"id": str(id), "name": name} for id, name in teams[:200]],
                "repositories": [
                    {"id": str(id), "name": f"{owner}/{name}"}
                    for id, owner, name in repositories[:200]
                ],
                "projects": [{"id": name, "name": name} for name in projects[:200]],
                "truncated": any(len(items) > 200 for items in (teams, repositories, projects)),
            }
