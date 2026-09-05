import builtins
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.agent_configuration import AgentConfigCommand, AgentView
from app.db.models import AgentConfig, Job, JobRole, JobState, Task, WorkerRun
from app.domain.agents import agent_status


class SqlAlchemyAgentConfigurationWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[AgentView]:
        configs = list((await self._session.scalars(select(AgentConfig))).all())
        existing = {config.role for config in configs}
        for role in JobRole:
            if role not in existing:
                configs.append(
                    AgentConfig(
                        role=role,
                        provider="openai",
                        model="",
                        enabled=True,
                        configuration={},
                        updated_at=datetime.now(UTC),
                    )
                )
        return await self._views(sorted(configs, key=lambda item: item.role.value))

    async def update(self, command: AgentConfigCommand) -> AgentView:
        role = JobRole(command.role)
        config = await self._session.get(AgentConfig, role)
        if config is None:
            config = AgentConfig(role=role)
            self._session.add(config)
        config.enabled = command.enabled
        config.provider = command.provider
        config.model = command.model
        config.configuration = command.configuration
        await self._session.commit()
        await self._session.refresh(config)
        return (await self._views([config]))[0]

    async def _views(self, configs: builtins.list[AgentConfig]) -> builtins.list[AgentView]:
        roles = [config.role for config in configs]
        totals = {
            row[0]: row[1:]
            for row in (
                await self._session.execute(
                    select(
                        WorkerRun.role,
                        func.count(WorkerRun.id),
                        func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                        func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                        func.coalesce(func.sum(WorkerRun.estimated_cost_usd), 0),
                    )
                    .where(WorkerRun.role.in_(roles))
                    .group_by(WorkerRun.role)
                )
            ).all()
        }
        latest_ranked = select(
            WorkerRun.role,
            WorkerRun.created_at,
            WorkerRun.duration_ms,
            WorkerRun.provider,
            WorkerRun.model,
            func.row_number()
            .over(partition_by=WorkerRun.role, order_by=WorkerRun.created_at.desc())
            .label("rank"),
        ).subquery()
        latest = {
            row[0]: row[1:]
            for row in (
                await self._session.execute(select(latest_ranked).where(latest_ranked.c.rank == 1))
            ).all()
        }
        active_ranked = (
            select(
                Job.role,
                Job.task_id,
                func.count(Job.id).over(partition_by=Job.role).label("active_count"),
                func.row_number()
                .over(partition_by=Job.role, order_by=Job.started_at.desc().nullslast())
                .label("rank"),
            )
            .where(Job.role.in_(roles), Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
            .subquery()
        )
        active = {
            row[0]: row[1:]
            for row in (
                await self._session.execute(
                    select(active_ranked, Task)
                    .join(Task, Task.id == active_ranked.c.task_id)
                    .where(active_ranked.c.rank == 1)
                )
            ).all()
        }
        views = []
        for config in configs:
            role_totals = totals.get(config.role, (0, 0, 0, 0))
            last = latest.get(config.role)
            current = active.get(config.role)
            active_count = int(current[1]) if current else 0
            task = current[3] if current else None
            views.append(
                AgentView(
                    config.role.value,
                    config.enabled,
                    config.provider,
                    config.model,
                    config.configuration,
                    config.updated_at,
                    agent_status(
                        enabled=config.enabled, model=config.model, active_jobs=active_count
                    ),
                    active_count,
                    int(role_totals[0]),
                    int(role_totals[1]),
                    int(role_totals[2]),
                    float(role_totals[3]),
                    last[0] if last else None,
                    last[1] if last else None,
                    last[2] if last else None,
                    last[3] if last else None,
                    str(task.id) if task else None,
                    task.manual_takeover if task else False,
                    bool(task and task.workspace_path),
                )
            )
        return views
