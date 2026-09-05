from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.agent_configuration import AgentConfigCommand, AgentView
from app.db.models import AgentConfig, Job, JobRole, JobState, WorkerRun
from app.domain.agents import agent_status


class SqlAlchemyAgentConfigurationWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[AgentView]:
        configs = list((await self._session.scalars(select(AgentConfig))).all())
        existing = {config.role for config in configs}
        for role in JobRole:
            if role not in existing:
                config = AgentConfig(role=role, provider="openai", model="", enabled=True)
                self._session.add(config)
                configs.append(config)
        if len(existing) != len(JobRole):
            await self._session.commit()
        return [
            await self._view(config) for config in sorted(configs, key=lambda item: item.role.value)
        ]

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
        return await self._view(config)

    async def _view(self, config: AgentConfig) -> AgentView:
        totals = (
            await self._session.execute(
                select(
                    func.count(WorkerRun.id),
                    func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.estimated_cost_usd), 0),
                ).where(WorkerRun.role == config.role)
            )
        ).one()
        latest = await self._session.scalar(
            select(WorkerRun)
            .where(WorkerRun.role == config.role)
            .order_by(WorkerRun.created_at.desc())
            .limit(1)
        )
        active_jobs = int(
            await self._session.scalar(
                select(func.count(Job.id)).where(
                    Job.role == config.role, Job.state.in_([JobState.CLAIMED, JobState.RUNNING])
                )
            )
            or 0
        )
        return AgentView(
            config.role.value,
            config.enabled,
            config.provider,
            config.model,
            config.configuration,
            config.updated_at,
            agent_status(enabled=config.enabled, model=config.model, active_jobs=active_jobs),
            active_jobs,
            int(totals[0]),
            int(totals[1]),
            int(totals[2]),
            float(totals[3]),
            latest.created_at if latest else None,
            latest.duration_ms if latest else None,
            latest.provider if latest else None,
            latest.model if latest else None,
        )
