import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import (
    AgentConfig,
    IndexStatus,
    Integration,
    IntegrationStatus,
    Job,
    JobRole,
    JobState,
    Repository,
    WebhookDelivery,
    WorkerNode,
    WorkerRun,
)
from app.db.session import get_session
from app.integrations.github import GitHubClient
from app.integrations.github_auth import (
    create_install_state,
    github_app_install_url,
    resolve_github_auth,
    verify_install_state,
)
from app.integrations.linear import LinearClient
from app.providers import create_provider
from app.schemas import (
    AgentConfigRead,
    AgentConfigUpdate,
    DashboardActivityRead,
    DiscoveredRepository,
    IntegrationRead,
    IntegrationUpdate,
    KnowledgeSearchResult,
    LinearWorkflowStateRead,
    ProviderCatalogRead,
    RepositoryCreate,
    RepositoryRead,
    WebhookHealthRead,
    WorkerNodeRead,
)
from app.services.crypto import cipher
from app.services.indexing import semantic_search

router = APIRouter(tags=["control-plane"])


@router.get("/activity", response_model=DashboardActivityRead)
async def dashboard_activity(session: AsyncSession = Depends(get_session)) -> DashboardActivityRead:
    active_job = await session.scalar(
        select(Job)
        .where(Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
        .order_by(Job.started_at, Job.created_at)
        .limit(1)
    )
    queued_jobs = list(
        (
            await session.scalars(
                select(Job)
                .where(Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT]))
                .order_by(Job.priority, Job.created_at)
                .limit(20)
            )
        ).all()
    )
    return DashboardActivityRead(active_job=active_job, queued_jobs=queued_jobs)


@router.get("/webhook-health", response_model=list[WebhookHealthRead])
async def webhook_health(session: AsyncSession = Depends(get_session)) -> list[WebhookHealthRead]:
    health: list[WebhookHealthRead] = []
    for provider in ("github", "linear"):
        pending = await session.scalar(
            select(func.count(WebhookDelivery.id)).where(
                WebhookDelivery.provider == provider, WebhookDelivery.status == "RECEIVED"
            )
        )
        failed = await session.scalar(
            select(func.count(WebhookDelivery.id)).where(
                WebhookDelivery.provider == provider, WebhookDelivery.status == "FAILED"
            )
        )
        latest = await session.scalar(
            select(WebhookDelivery)
            .where(WebhookDelivery.provider == provider)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(1)
        )
        latest_error = await session.scalar(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.provider == provider,
                WebhookDelivery.last_error.is_not(None),
            )
            .order_by(WebhookDelivery.created_at.desc())
            .limit(1)
        )
        health.append(
            WebhookHealthRead(
                provider=provider,
                pending=int(pending or 0),
                failed=int(failed or 0),
                last_delivery_at=latest.created_at if latest else None,
                last_processed_at=latest.processed_at if latest else None,
                last_error=latest_error.last_error if latest_error else None,
            )
        )
    return health


@router.get("/providers/{provider_name}/catalog", response_model=ProviderCatalogRead)
async def provider_catalog(
    provider_name: str,
    session: AsyncSession = Depends(get_session),
) -> ProviderCatalogRead:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == provider_name)
    )
    if integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail=f"Configure {provider_name} credentials first")
    try:
        provider = create_provider(provider_name, cipher.decrypt(integration.encrypted_credentials))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    models = await provider.list_models()
    return ProviderCatalogRead(
        provider=provider_name,
        capabilities=provider.capabilities(),
        models=[{"id": model.id, "display_name": model.display_name} for model in models],
    )


@router.get("/workers", response_model=list[WorkerNodeRead])
async def list_workers(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[WorkerNodeRead]:
    workers = list(
        (await session.scalars(select(WorkerNode).order_by(WorkerNode.started_at.desc()))).all()
    )
    stale_before = datetime.now(UTC) - timedelta(seconds=settings.worker_heartbeat_seconds * 3)
    return [
        WorkerNodeRead(
            id=worker.id,
            hostname=worker.hostname,
            process_id=worker.process_id,
            status=worker.status,
            online=worker.status == "ONLINE" and worker.last_heartbeat >= stale_before,
            capabilities=worker.capabilities,
            started_at=worker.started_at,
            last_heartbeat=worker.last_heartbeat,
            stopped_at=worker.stopped_at,
        )
        for worker in workers
    ]


@router.get("/github/repositories", response_model=list[DiscoveredRepository])
async def discover_github_repositories(
    session: AsyncSession = Depends(get_session),
) -> list[DiscoveredRepository]:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail="Configure GitHub credentials first")
    auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
    client = GitHubClient(auth.token, auth.installation)
    return await client.list_repositories()


@router.get("/github/app/install-url")
async def github_install_url(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    slug = integration.configuration.get("app_slug") if integration else None
    if not integration or not integration.encrypted_credentials or not isinstance(slug, str):
        raise HTTPException(status_code=409, detail="Save GitHub App credentials and slug first")
    try:
        url = github_app_install_url(slug, create_install_state(settings.app_secret_key))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"url": url}


@router.get("/github/app/callback", response_model=None)
async def github_install_callback(
    installation_id: str = Query(min_length=1, pattern=r"^[0-9]+$"),
    state: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not verify_install_state(settings.app_secret_key, state):
        raise HTTPException(status_code=400, detail="Invalid or expired GitHub installation state")
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail="GitHub App credentials are not configured")
    try:
        credential = json.loads(cipher.decrypt(integration.encrypted_credentials))
        if not isinstance(credential, dict) or credential.get("auth_type") != "github_app":
            raise ValueError("GitHub integration is not configured as an App")
        credential["installation_id"] = installation_id
        integration.encrypted_credentials = cipher.encrypt(json.dumps(credential))
        auth = await resolve_github_auth(json.dumps(credential))
        await GitHubClient(auth.token, auth.installation).list_repositories()
    except (httpx.HTTPError, TypeError, ValueError, json.JSONDecodeError) as exc:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = str(exc)[:2000]
        await session.commit()
        return RedirectResponse(f"{settings.github_app_return_url}?github=error", status_code=303)
    integration.status = IntegrationStatus.CONNECTED
    integration.last_error = None
    await session.commit()
    return RedirectResponse(f"{settings.github_app_return_url}?github=connected", status_code=303)


@router.get("/linear/workflow-states", response_model=list[LinearWorkflowStateRead])
async def discover_linear_workflow_states(
    session: AsyncSession = Depends(get_session),
) -> list[LinearWorkflowStateRead]:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "linear")
    )
    if integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail="Configure Linear credentials first")
    client = LinearClient(cipher.decrypt(integration.encrypted_credentials))
    return [LinearWorkflowStateRead(**state) for state in await client.list_workflow_states()]


@router.get("/integrations", response_model=list[IntegrationRead])
async def list_integrations(session: AsyncSession = Depends(get_session)) -> list[Integration]:
    return list(
        (await session.scalars(select(Integration).order_by(Integration.provider_name))).all()
    )


@router.put("/integrations/{provider_name}", response_model=IntegrationRead)
async def configure_integration(
    provider_name: str,
    body: IntegrationUpdate,
    session: AsyncSession = Depends(get_session),
) -> Integration:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == provider_name)
    )
    if integration is None:
        integration = Integration(provider_name=provider_name, provider_type=body.provider_type)
        session.add(integration)
    integration.provider_type = body.provider_type
    integration.status = body.status
    integration.configuration = body.configuration
    if body.credential is not None:
        integration.encrypted_credentials = cipher.encrypt(body.credential.get_secret_value())
    integration.last_error = None
    await session.commit()
    await session.refresh(integration)
    return integration


@router.post("/integrations/{provider_name}/test", response_model=IntegrationRead)
async def test_integration(
    provider_name: str,
    session: AsyncSession = Depends(get_session),
) -> Integration:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == provider_name)
    )
    if integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail="Configure credentials first")
    credential = cipher.decrypt(integration.encrypted_credentials)
    try:
        if provider_name == "github":
            auth = await resolve_github_auth(credential)
            await GitHubClient(auth.token, auth.installation).list_repositories()
        elif provider_name == "linear":
            await LinearClient(credential).list_workflow_states()
        elif provider_name in {"openai", "anthropic", "google"}:
            await create_provider(provider_name, credential).list_models()
        elif provider_name in {"npm_registry", "pypi_registry"}:
            if not credential.strip():
                raise ValueError("Registry token cannot be empty")
        else:
            raise ValueError(f"Unsupported integration: {provider_name}")
    except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
        integration.status = IntegrationStatus.ERROR
        integration.last_error = str(exc)[:2000]
        await session.commit()
        return integration
    integration.status = IntegrationStatus.CONNECTED
    integration.last_error = None
    await session.commit()
    return integration


@router.get("/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    session: AsyncSession = Depends(get_session),
) -> list[RepositoryRead]:
    repositories = list(
        (
            await session.scalars(select(Repository).order_by(Repository.owner, Repository.name))
        ).all()
    )
    result: list[RepositoryRead] = []
    for repository in repositories:
        chunk_count = int(
            await session.scalar(
                text(
                    "SELECT count(*) FROM knowledge_chunks WHERE repository_id = :repository_id"
                ).bindparams(repository_id=repository.id)
            )
            or 0
        )
        result.append(
            RepositoryRead.model_validate(repository).model_copy(
                update={
                    "clone_status": "CLONED"
                    if repository.local_path and repository.latest_sha
                    else "NOT_CLONED",
                    "chunk_count": chunk_count,
                },
            )
        )
    return result


@router.post("/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepositoryCreate, session: AsyncSession = Depends(get_session)
) -> Repository:
    repository = Repository(
        **body.model_dump(),
        index_status=IndexStatus.QUEUED,
        index_error=None,
    )
    session.add(repository)
    await session.commit()
    await session.refresh(repository)
    return repository


@router.patch("/repositories/{repository_id}/enabled", response_model=RepositoryRead)
async def set_repository_enabled(
    repository_id: uuid.UUID,
    enabled: bool,
    session: AsyncSession = Depends(get_session),
) -> Repository:
    repository = await session.get(Repository, repository_id, with_for_update=True)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    repository.enabled = enabled
    if enabled:
        repository.index_status = IndexStatus.QUEUED
        repository.index_error = None
    await session.commit()
    return repository


@router.post("/repositories/{repository_id}/index", response_model=RepositoryRead)
async def queue_repository_index(
    repository_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Repository:
    repository = await session.get(Repository, repository_id, with_for_update=True)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if not repository.enabled:
        raise HTTPException(status_code=409, detail="Repository is disabled")
    repository.index_status = IndexStatus.QUEUED
    repository.index_error = None
    await session.commit()
    return repository


@router.get("/repositories/{repository_id}/search", response_model=list[KnowledgeSearchResult])
async def search_repository_knowledge(
    repository_id: uuid.UUID,
    query: str,
    limit: int = 8,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    repository = await session.get(Repository, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if repository.index_status.value != "READY":
        raise HTTPException(status_code=409, detail="Repository index is not ready")
    return await semantic_search(session, repository_id, query, min(max(limit, 1), 20))


@router.get("/agents", response_model=list[AgentConfigRead])
async def list_agent_configs(
    session: AsyncSession = Depends(get_session),
) -> list[AgentConfigRead]:
    configs = list((await session.scalars(select(AgentConfig))).all())
    existing = {config.role for config in configs}
    for role in JobRole:
        if role not in existing:
            config = AgentConfig(role=role, provider="openai", model="", enabled=True)
            session.add(config)
            configs.append(config)
    if len(existing) != len(JobRole):
        await session.commit()
    result: list[AgentConfigRead] = []
    for config in sorted(configs, key=lambda item: item.role.value):
        totals = (
            await session.execute(
                select(
                    func.count(WorkerRun.id),
                    func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.estimated_cost_usd), 0),
                ).where(WorkerRun.role == config.role)
            )
        ).one()
        latest = await session.scalar(
            select(WorkerRun)
            .where(WorkerRun.role == config.role)
            .order_by(WorkerRun.created_at.desc())
            .limit(1)
        )
        active_jobs = int(
            await session.scalar(
                select(func.count(Job.id)).where(
                    Job.role == config.role,
                    Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
                )
            )
            or 0
        )
        if not config.enabled:
            agent_status = "DISABLED"
        elif not config.model:
            agent_status = "NEEDS_CONFIGURATION"
        elif active_jobs:
            agent_status = "RUNNING"
        else:
            agent_status = "READY"
        result.append(
            AgentConfigRead(
                role=config.role,
                enabled=config.enabled,
                provider=config.provider,
                model=config.model,
                configuration=config.configuration,
                updated_at=config.updated_at,
                status=agent_status,
                active_jobs=active_jobs,
                total_runs=int(totals[0]),
                total_input_tokens=int(totals[1]),
                total_output_tokens=int(totals[2]),
                total_estimated_cost_usd=float(totals[3]),
                last_run_at=latest.created_at if latest else None,
                last_duration_ms=latest.duration_ms if latest else None,
                last_provider=latest.provider if latest else None,
                last_model=latest.model if latest else None,
            )
        )
    return result


@router.put("/agents/{role}", response_model=AgentConfigRead)
async def update_agent_config(
    role: JobRole,
    body: AgentConfigUpdate,
    session: AsyncSession = Depends(get_session),
) -> AgentConfig:
    config = await session.get(AgentConfig, role)
    if config is None:
        config = AgentConfig(role=role)
        session.add(config)
    config.enabled = body.enabled
    config.provider = body.provider
    config.model = body.model
    config.configuration = body.configuration
    await session.commit()
    await session.refresh(config)
    return config
