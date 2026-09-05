import asyncio
import json
import sys
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentConfig,
    Integration,
    Job,
    JobRole,
    Repository,
    Task,
    WorkerRun,
)
from app.db.session import SessionLocal
from app.logging import configure_logging
from app.providers import ProviderRequest, create_provider
from app.schemas import WorkerResult
from app.services.context_compiler import ContextCompiler
from app.services.crypto import cipher
from app.services.executor import (
    ExecutorProposal,
    ReviewerProposal,
    apply_proposal,
    changed_files,
    run_checks,
    workspace_fingerprint,
)
from app.services.structured_output import (
    ProviderAttempt,
    StructuredOutputError,
    run_with_structured_repair,
)
from app.services.workspaces import prepare_workspace, run_git

ROLE_INSTRUCTIONS = {
    "INTAKE": "Normalize the supplied event. Return concise JSON with result EVENT_INTERPRETED; event_type (NEW_TASK, INFORMATIONAL, REVIEW_FIX, ARCHITECTURAL_FINDING, REQUIREMENT_CHANGE, or NEEDS_HUMAN); actionability (ACTION_REQUIRED, INFORMATIONAL, or NEEDS_HUMAN); blocking; summary; and confidence. Classify ordinary concrete review fixes as REVIEW_FIX, architecture/design changes as ARCHITECTURAL_FINDING, changed requirements as REQUIREMENT_CHANGE, and harmless messages as INFORMATIONAL.",
    "THINKER": "Act as the technical planning agent. Return concise JSON with result (PLAN_READY, NEEDS_CONTEXT, or NEEDS_HUMAN), goal, targets, ordered_steps, constraints, required_tests, risks, acceptance_criteria, reason, and questions. PLAN_READY requires a concrete goal, steps, and acceptance criteria. NEEDS_CONTEXT requires a reason and precise questions. NEEDS_HUMAN requires a reason. Escalate ambiguity instead of inventing requirements. Do not modify code.",
    "EXECUTOR": "Act as the implementation agent. Return only JSON matching: {result, summary, files: [{path, content}], delete_files: [], plan_mismatch, reason}. result must be IMPLEMENTED, PLAN_MISMATCH, BLOCKED, NEEDS_REPLAN, or NEEDS_HUMAN. Only IMPLEMENTED may contain file changes. PLAN_MISMATCH and NEEDS_REPLAN require plan_mismatch details; BLOCKED and NEEDS_HUMAN require a reason. Supply complete file contents. Modify only files needed for the task; never include secrets, generated dependencies, lockfiles unless necessary, or paths outside the repository.",
    "REVIEWER": "Act as an independent code reviewer. Inspect the supplied task, plan, and actual Git diff. Return only JSON matching {result, summary, findings: [{severity, path, line, message}], reason}. result must be PASS, FAIL_ACTIONABLE, FAIL_ARCHITECTURAL, UNCERTAIN, or NEEDS_HUMAN. PASS has no findings. Failure outcomes require concrete findings. UNCERTAIN and NEEDS_HUMAN require a reason. Report only evidenced correctness, security, architectural, regression, or missing-test problems; do not invent evidence.",
}


async def package_registry_environment(session: AsyncSession) -> dict[str, str]:
    environment: dict[str, str] = {}
    integrations = list(
        (
            await session.scalars(
                select(Integration).where(
                    Integration.provider_name.in_(["npm_registry", "pypi_registry"])
                )
            )
        ).all()
    )
    for integration in integrations:
        if integration.encrypted_credentials is None:
            continue
        token = cipher.decrypt(integration.encrypted_credentials)
        if integration.provider_name == "npm_registry":
            environment["NODE_AUTH_TOKEN"] = token
            registry = integration.configuration.get("registry_url")
            if isinstance(registry, str) and registry.startswith("https://"):
                environment["NPM_CONFIG_REGISTRY"] = registry
        else:
            environment["UV_INDEX_USERNAME"] = "__token__"
            environment["UV_INDEX_PASSWORD"] = token
            index = integration.configuration.get("index_url")
            if isinstance(index, str) and index.startswith("https://"):
                environment["UV_DEFAULT_INDEX"] = index
    return environment


def estimate_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
    configuration: dict[str, Any],
) -> float | None:
    try:
        input_rate = float(configuration["input_cost_per_million"])
        output_rate = float(configuration["output_cost_per_million"])
    except (KeyError, TypeError, ValueError):
        return None
    if input_rate < 0 or output_rate < 0:
        return None
    return round(
        ((input_tokens or 0) * input_rate + (output_tokens or 0) * output_rate) / 1_000_000,
        6,
    )


async def persist_attempts(
    session: AsyncSession,
    job: Job,
    provider_name: str,
    model: str,
    attempts: list[ProviderAttempt],
    configuration: dict[str, Any],
) -> None:
    for attempt in attempts:
        session.add(
            WorkerRun(
                job_id=job.id,
                role=job.role,
                provider=provider_name,
                model=model,
                input_tokens=attempt.response.input_tokens,
                output_tokens=attempt.response.output_tokens,
                estimated_cost_usd=estimate_cost_usd(
                    attempt.response.input_tokens,
                    attempt.response.output_tokens,
                    configuration,
                ),
                duration_ms=attempt.duration_ms,
                provider_request_id=attempt.response.request_id,
            )
        )
    await session.commit()


async def run(job_id: uuid.UUID) -> WorkerResult:
    async with SessionLocal() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        task = await session.get(Task, job.task_id)
        config = await session.get(AgentConfig, job.role)
        if task is None:
            raise RuntimeError(f"Task {job.task_id} not found")
        if config is None or not config.enabled or not config.model:
            raise RuntimeError(f"Agent {job.role.value} is not fully configured")
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == config.provider)
        )
        if integration is None or integration.encrypted_credentials is None:
            raise RuntimeError(f"Provider {config.provider} has no stored credential")
        provider = create_provider(
            config.provider, cipher.decrypt(integration.encrypted_credentials)
        )
        repository = (
            await session.get(Repository, task.repository_id) if task.repository_id else None
        )
        workspace = None
        if job.role in {JobRole.EXECUTOR, JobRole.REVIEWER}:
            if task.repository_id is None:
                raise RuntimeError(f"{job.role.value} task has no repository")
            if repository is None or not repository.enabled:
                raise RuntimeError(f"{job.role.value} repository is unavailable")
            workspace = await prepare_workspace(session, task, repository)
        configured_limit = config.configuration.get("max_context_chars", 160_000)
        max_context_chars = (
            int(configured_limit) if isinstance(configured_limit, (int, str)) else 160_000
        )
        compiler = ContextCompiler(session, max_context_chars)
        if job.role == JobRole.INTAKE:
            prompt_data = await compiler.compile_for_intake(task, job)
        elif job.role == JobRole.THINKER:
            prompt_data = await compiler.compile_for_thinker(task, job, repository)
        elif job.role == JobRole.EXECUTOR and repository is not None and workspace is not None:
            prompt_data = await compiler.compile_for_executor(task, job, repository, workspace)
        elif job.role == JobRole.REVIEWER and repository is not None and workspace is not None:
            prompt_data = await compiler.compile_for_reviewer(task, job, repository, workspace)
        else:
            raise RuntimeError(f"Unsupported worker role {job.role.value}")
        prompt = json.dumps(prompt_data, ensure_ascii=False)
        configured_repairs = config.configuration.get("structured_output_retries", 2)
        max_repairs = int(configured_repairs) if isinstance(configured_repairs, (int, str)) else 2
        try:
            data, attempts = await run_with_structured_repair(
                provider,
                ProviderRequest(
                    model=config.model,
                    system=ROLE_INSTRUCTIONS[job.role.value],
                    prompt=prompt,
                ),
                job.role,
                max_repairs,
            )
        except StructuredOutputError as exc:
            await persist_attempts(
                session, job, config.provider, config.model, exc.attempts, config.configuration
            )
            raise
        await persist_attempts(
            session, job, config.provider, config.model, attempts, config.configuration
        )
        result = "MODEL_COMPLETED"
        summary = str(data.get("summary") or data.get("goal") or "Model completed")[:500]
        if job.role == JobRole.INTAKE:
            result = str(data["result"])
            summary = str(data["summary"])[:500]
        elif job.role == JobRole.THINKER:
            result = str(data["result"])
            summary = str(data.get("goal") or data.get("reason") or "Thinker completed")[:500]
        elif job.role == JobRole.EXECUTOR and workspace is not None:
            proposal = ExecutorProposal.model_validate(data)
            if proposal.result != "IMPLEMENTED":
                result = proposal.result
                summary = proposal.summary
                data = proposal.model_dump(mode="json")
            else:
                apply_proposal(workspace, proposal)
                checks = await run_checks(
                    workspace, credential_environment=await package_registry_environment(session)
                )
                files = await changed_files(workspace)
                revision = await run_git("rev-parse", "HEAD", cwd=workspace)
                checks_passed = all(check.passed for check in checks)
                result = "IMPLEMENTED" if checks_passed else "TEST_FAILED"
                summary = proposal.summary
                data = {
                    "changed_files": files,
                    "workspace_revision": revision,
                    "workspace_fingerprint": await workspace_fingerprint(workspace),
                    "checks": [check.model_dump(mode="json") for check in checks],
                    "plan_mismatch": proposal.plan_mismatch,
                }
        elif job.role == JobRole.REVIEWER:
            review = ReviewerProposal.model_validate(data)
            result = review.result
            summary = review.summary
            data = review.model_dump(mode="json")
        return WorkerResult(
            job_id=job.id,
            task_id=job.task_id,
            role=job.role,
            result=result,
            summary=summary,
            data=data,
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.worker JOB_ID")
    configure_logging()
    output = asyncio.run(run(uuid.UUID(sys.argv[1])))
    print(output.model_dump_json())
