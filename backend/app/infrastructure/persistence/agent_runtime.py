import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.agent_runtime import AgentRuntimeNotFound
from app.db.models import AIAgent, Role
from app.domain.ai_runtime import EffectiveAgentRuntimeConfig, resolve_runtime_config
from app.providers.capabilities import ModelCapabilityRegistry

ALLOWED_RUNTIME_OVERRIDES = frozenset(
    {
        "reasoning_level",
        "max_output_tokens",
        "temperature",
        "context_strategy",
        "max_tool_calls",
        "job_timeout_seconds",
    }
)


class SqlAlchemyAgentRuntimeStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def effective(self, agent_id: uuid.UUID) -> dict[str, Any]:
        agent, role = await self._load(agent_id)
        return self._view(agent, role)

    async def update(self, agent_id: uuid.UUID, overrides: dict[str, Any]) -> dict[str, Any]:
        unknown = set(overrides) - ALLOWED_RUNTIME_OVERRIDES
        if unknown:
            raise ValueError(f"Unsupported runtime override: {min(unknown)}")
        agent, role = await self._load(agent_id)
        # Resolution is the activation-time validation: policy, ranges, and model capabilities.
        self._resolve(agent, role, overrides)
        agent.runtime_overrides = dict(overrides)
        agent.config_version += 1
        await self._session.commit()
        return self._view(agent, role)

    async def reset(self, agent_id: uuid.UUID) -> dict[str, Any]:
        agent, role = await self._load(agent_id)
        agent.runtime_overrides = {}
        agent.config_version += 1
        await self._session.commit()
        return self._view(agent, role)

    async def _load(self, agent_id: uuid.UUID) -> tuple[AIAgent, Role]:
        agent = await self._session.get(AIAgent, agent_id)
        if agent is None:
            raise AgentRuntimeNotFound("Agent not found")
        role = await self._session.get(Role, agent.role_id)
        if role is None or role.archived_at is not None:
            raise AgentRuntimeNotFound("Agent Role not found")
        return agent, role

    @staticmethod
    def _resolve(
        agent: AIAgent, role: Role, overrides: dict[str, Any] | None = None
    ) -> EffectiveAgentRuntimeConfig:
        provider = agent.provider or role.default_provider or "openai"
        model = agent.model or role.default_model or ""
        return resolve_runtime_config(
            provider=provider,
            model=model,
            role_profile=dict(role.runtime_profile or {}),
            agent_overrides=dict(agent.runtime_overrides if overrides is None else overrides),
            override_policy=dict(role.override_policy or {}),
            strategy=None,
            capabilities=ModelCapabilityRegistry().get(provider, model),
        )

    def _view(self, agent: AIAgent, role: Role) -> dict[str, Any]:
        runtime = self._resolve(agent, role)
        return {
            "agent_id": str(agent.id),
            "role_id": str(role.id),
            "role_name": role.name,
            "config_version": agent.config_version,
            "overrides": dict(agent.runtime_overrides or {}),
            "effective": runtime.snapshot(),
            "effective_hash": runtime.fingerprint(),
            "sources": {
                key: "AGENT" if key in (agent.runtime_overrides or {}) else "ROLE"
                for key in runtime.snapshot()
            },
        }
