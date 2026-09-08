from dataclasses import asdict
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from app.agent_runtime.application.sessions import (
    ChangeSession,
    SessionAdministration,
    SessionConflict,
    SessionView,
)
from app.agent_runtime.application.token_efficiency import TokenEfficiencyQueries
from app.agent_runtime.domain.session_changes import SessionChangeMode
from app.bootstrap.v2 import (
    automation_admin,
    session_administration,
    team_profiles,
    token_efficiency,
)
from app.platform.configuration.settings import get_settings
from app.teams.application.automation import AutomationAdmin
from app.teams.application.profiles import (
    ManageProfiles,
    ProfileConflict,
    ProfileView,
    TeamProfiles,
)
from app.teams.domain.automation import AutomationPolicy
from app.teams.domain.profiles import AgentProfile, RoleKind

router = APIRouter(prefix="/v2", tags=["engineering-v2"])


class TokenPolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    values: dict[str, Any]


class ContextRolloverWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=2000)


@router.get("/tasks/{task_id}/token-efficiency-policy")
async def read_task_token_policy(
    task_id: UUID, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> dict[str, Any]:
    try:
        return await store.task_policy(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/tasks/{task_id}/token-efficiency-policy")
async def write_task_token_policy(
    task_id: UUID, body: TokenPolicyWrite, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> dict[str, Any]:
    try:
        return await store.save_task_policy(task_id, body.version, body.values)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            409, "Invalid/stale task policy or task is not safely suspended"
        ) from exc


@router.post("/tasks/{task_id}/context-rollover")
async def rollover_context(
    task_id: UUID,
    body: ContextRolloverWrite,
    store: TokenEfficiencyQueries = Depends(token_efficiency),
) -> dict[str, Any]:
    try:
        return await store.rollover(task_id, body.requirement_version, body.note)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(
            409,
            "Rollover blocked: verify suspended state, reconciled billing, workspace and bounded note",
        ) from exc


@router.get("/teams/{team_id}/token-efficiency-policy")
async def read_token_policy(
    team_id: UUID, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> dict[str, Any]:
    try:
        return await store.policy(team_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/teams/{team_id}/token-efficiency-policy")
async def write_token_policy(
    team_id: UUID, body: TokenPolicyWrite, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> dict[str, Any]:
    try:
        return await store.save_policy(team_id, body.version, body.values)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Invalid or stale token policy; reload and check limits") from exc


@router.get("/tasks/{task_id}/token-efficiency")
async def task_token_efficiency(
    task_id: UUID, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> dict[str, Any]:
    try:
        return await store.task(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/tasks/{task_id}/context-generations")
async def context_generations(
    task_id: UUID, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> list[dict[str, Any]]:
    try:
        return await store.generations(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/tasks/{task_id}/checkpoints")
async def developer_checkpoints(
    task_id: UUID, store: TokenEfficiencyQueries = Depends(token_efficiency)
) -> list[dict[str, Any]]:
    try:
        return await store.checkpoints(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


class SessionChangeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    lifecycle_version: int = Field(ge=1)
    profile_version: int = Field(ge=1)
    mode: SessionChangeMode
    reason: str = Field(min_length=3, max_length=500)


@router.get("/tasks/{task_id}/session")
async def developer_session(
    task_id: UUID, store: SessionAdministration = Depends(session_administration)
) -> SessionView | None:
    try:
        return await store.read(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SessionConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/tasks/{task_id}/session/change")
async def change_developer_session(
    task_id: UUID,
    body: SessionChangeWrite,
    store: SessionAdministration = Depends(session_administration),
) -> SessionView:
    try:
        return await store.change(task_id, ChangeSession(**body.model_dump()))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SessionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class PriceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["openai", "anthropic", "deepseek"]
    model: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=80)
    context_tier: Literal["standard"] = "standard"
    service_tier: Literal["standard"] = "standard"
    input_per_million: Decimal = Field(gt=0, le=10000, allow_inf_nan=False)
    output_per_million: Decimal = Field(gt=0, le=10000, allow_inf_nan=False)
    cached_input_per_million: Decimal | None = Field(
        default=None, ge=0, le=10000, allow_inf_nan=False
    )
    cache_write_per_million: Decimal | None = Field(
        default=None, ge=0, le=10000, allow_inf_nan=False
    )
    source_url: HttpUrl
    effective_at: AwareDatetime


class CostReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_usd: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    evidence_reference: str = Field(min_length=3, max_length=500)


@router.post("/runs/{run_id}/reconcile-cost")
async def reconcile_cost(
    run_id: UUID, body: CostReconciliation, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, str]:
    try:
        await store.reconcile_cost(run_id, body.amount_usd, body.evidence_reference)
        return {"status": "reconciled", "usage_counters": "unchanged"}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProfileConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/statistics")
async def usage_statistics(
    team_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=90),
    store: AutomationAdmin = Depends(automation_admin),
) -> dict[str, Any]:
    try:
        return await store.statistics(team_id, days)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/pricing")
async def prices(store: AutomationAdmin = Depends(automation_admin)) -> list[dict[str, Any]]:
    return await store.list_prices()


@router.post("/pricing", status_code=201)
async def add_price(
    body: PriceWrite, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, str]:
    values = body.model_dump()
    values["source_url"] = str(body.source_url)
    try:
        return {"id": str(await store.add_price(values))}
    except ProfileConflict as exc:
        raise HTTPException(409, str(exc)) from exc


class AutomationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    enrollment_enabled: bool = False
    auto_merge: bool = False
    repository_ids: list[UUID] = Field(default_factory=list, max_length=100)
    authorized_reviewer_ids: list[str] = Field(default_factory=list, max_length=100)
    required_checks: list[str] = Field(default_factory=list, max_length=100)
    task_budget_usd: Decimal = Field(gt=0, le=10000, allow_inf_nan=False)
    team_budget_usd: Decimal = Field(gt=0, le=10000, allow_inf_nan=False)
    require_formal_approval: bool = True
    reviewer_scope: Literal["allowlist", "any_human"] = "allowlist"


@router.get("/teams/{team_id}/automation")
async def automation(
    team_id: UUID, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, Any]:
    try:
        policy, version = await store.read(team_id)
        return {**asdict(policy), "version": version}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/teams/{team_id}/automation")
async def save_automation(
    team_id: UUID, body: AutomationWrite, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, int]:
    try:
        policy = AutomationPolicy(**body.model_dump(exclude={"version"}))
        return {"version": await store.save(team_id, policy, body.version)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProfileConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/tasks/{task_id}/enroll", status_code=202)
async def enroll_task(
    task_id: UUID, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, str]:
    try:
        await store.enroll(task_id)
        return {"status": "enrolled"}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/tasks/{task_id}/retry-status-sync", status_code=202)
async def retry_status_sync(
    task_id: UUID, store: AutomationAdmin = Depends(automation_admin)
) -> dict[str, str]:
    try:
        await store.retry_status_sync(task_id)
        return {"status": "queued", "ai_usage": "none"}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProfileConflict as exc:
        raise HTTPException(409, str(exc)) from exc


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=120)
    avatar: str = Field(default="", max_length=500)
    enabled: bool = True
    provider: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=255)
    harness: str | None = None
    effort: str = "medium"
    supplemental_instructions: str = Field(default="", max_length=8000)
    soft_budget_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    hard_budget_usd: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)


def profile_payload(value: ProfileView) -> dict[str, Any]:
    return {
        "id": str(value.id),
        "team_id": str(value.team_id),
        "version": value.version,
        **asdict(value.profile),
    }


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    settings = get_settings()
    return {
        "lifecycle": "fixed",
        "codex_enabled": settings.developer_harness_codex,
        "claude_enabled": settings.developer_harness_claude,
        "local_interpreter_enabled": settings.local_event_interpreter,
        "execution_requirements": [
            "enabled Team",
            "automation policy",
            "native runtime",
            "provider credential",
            "verified pricing",
            "validation commands",
        ],
        "phases": [
            "INTERPRET_EVENT",
            "DEVELOPER_TURN",
            "THINKER_TURN",
            "RUN_VALIDATION",
            "PUBLISH_PR",
            "MERGE_PR",
        ],
    }


@router.get("/teams/{team_id}/profiles")
async def profiles(
    team_id: UUID, store: TeamProfiles = Depends(team_profiles)
) -> list[dict[str, Any]]:
    try:
        return [profile_payload(item) for item in await store.list_profiles(team_id)]
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/teams/{team_id}/profiles/initialize")
async def initialize_profiles(
    team_id: UUID, store: TeamProfiles = Depends(team_profiles)
) -> list[dict[str, Any]]:
    try:
        return [profile_payload(item) for item in await ManageProfiles(store).initialize(team_id)]
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/teams/{team_id}/profiles/{role}")
async def save_profile(
    team_id: UUID, role: RoleKind, body: ProfileWrite, store: TeamProfiles = Depends(team_profiles)
) -> dict[str, Any]:
    try:
        profile = AgentProfile(role_kind=role, **body.model_dump(exclude={"version"}))
        return profile_payload(
            await ManageProfiles(store).save(team_id, role, profile, body.version)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProfileConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/teams/{team_id}/activity")
async def team_activity(
    team_id: UUID, store: TeamProfiles = Depends(team_profiles)
) -> dict[str, Any]:
    try:
        return await store.activity(team_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
