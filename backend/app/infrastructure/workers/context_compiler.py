import json
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IndexStatus, Job, JobRole, Repository, ReviewFinding, Task
from app.domain.memory import render_memory
from app.infrastructure.agent_knowledge import search_agent_knowledge
from app.infrastructure.git.workspaces import run_git
from app.infrastructure.indexing import semantic_search
from app.infrastructure.persistence.task_memory import TaskMemoryService
from app.infrastructure.workers.executor import repository_context

DEFAULT_CONTEXT_CHARS = 160_000
MIN_CONTEXT_CHARS = 20_000
MAX_CONTEXT_CHARS = 500_000


def fit_context(context: dict[str, Any], limit: int) -> dict[str, Any]:
    """Trim low-priority context while preserving valid structured JSON."""
    limit = min(max(limit, MIN_CONTEXT_CHARS), MAX_CONTEXT_CHARS)
    repository = context.get("repository")
    if isinstance(repository, dict):
        for key in ("files", "diff"):
            value = repository.get(key)
            if isinstance(value, str) and len(value) > limit // 2:
                repository[key] = value[: limit // 2] + "\n[TRUNCATED]"
    for key in ("retrieved_knowledge", "open_findings"):
        values = context.get(key)
        while isinstance(values, list) and values and len(json.dumps(context)) > limit:
            values.pop()
    task = context.get("task")
    if isinstance(task, dict) and len(json.dumps(context)) > limit:
        description = task.get("description")
        if isinstance(description, str) and len(description) > 4_000:
            task["description"] = description[:4_000] + "\n[TRUNCATED]"
    job = context.get("job")
    if isinstance(job, dict) and len(json.dumps(context)) > limit:
        job["payload"] = {"trimmed": True}
    if len(json.dumps(context)) > limit:
        raise ValueError("Essential worker context exceeds configured limit")
    return context


class ContextCompiler:
    def __init__(
        self,
        session: AsyncSession,
        max_chars: int = DEFAULT_CONTEXT_CHARS,
        include_repository_knowledge: bool = True,
        retrieval_depth: str = "normal",
    ) -> None:
        self.session = session
        self.max_chars = max_chars
        self.include_repository_knowledge = include_repository_knowledge
        self.retrieval_depth = retrieval_depth

    def _base(self, task: Task, job: Job) -> dict[str, Any]:
        return {
            "task": {
                "id": str(task.id),
                "external_key": task.external_key,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "state": task.state.value,
            },
            "job": {"id": str(job.id), "action": job.action, "payload": job.payload},
        }

    async def _persistent_memory(self, task: Task, role: JobRole) -> dict[str, Any]:
        return render_memory(await TaskMemoryService(self.session).load(task), role)

    async def _previous_checkpoint(self, task: Task, role: JobRole) -> dict[str, Any] | None:
        checkpoint = await TaskMemoryService(self.session).latest_checkpoint(task.id, role)
        if checkpoint is None:
            return None
        return {
            "id": str(checkpoint.id),
            "summary": checkpoint.summary,
            "repository_sha": checkpoint.repository_sha,
            "structured_data": checkpoint.structured_data,
            "stale": bool(
                checkpoint.repository_sha
                and task.current_revision
                and checkpoint.repository_sha != task.current_revision
            ),
        }

    async def _finish(
        self, task: Task, job: Job, context: dict[str, Any], started: float
    ) -> dict[str, Any]:
        fitted = fit_context(context, self.max_chars)
        serialized = json.dumps(fitted, ensure_ascii=False)
        memory = await TaskMemoryService(self.session).load(task)
        previous = fitted.get("previous_role_checkpoint")
        checkpoint_ids = [str(previous["id"])] if isinstance(previous, dict) else []
        findings = fitted.get("open_findings", [])
        finding_ids = [
            str(item["id"]) for item in findings if isinstance(item, dict) and "id" in item
        ]
        knowledge = fitted.get("retrieved_knowledge", [])
        rag_ids = [
            f"{item.get('file_path')}:{item.get('chunk_index')}"
            for item in knowledge
            if isinstance(item, dict)
        ]
        plan_id = memory.current_plan_job_id
        await TaskMemoryService(self.session).record_context(
            job,
            memory.version,
            task.current_revision,
            checkpoint_ids,
            uuid.UUID(plan_id) if plan_id else None,
            finding_ids,
            rag_ids,
            max(1, len(serialized) // 4),
            round((time.monotonic() - started) * 1000),
        )
        return fitted

    async def _knowledge(
        self, task: Task, repository: Repository | None, role: JobRole
    ) -> list[dict[str, Any]]:
        query = f"{task.title}\n{task.description}"
        rows: list[dict[str, Any]] = []
        if (
            self.include_repository_knowledge
            and repository is not None
            and repository.index_status == IndexStatus.READY
        ):
            repository_limit = {"low": 4, "normal": 8, "deep": 16}.get(self.retrieval_depth, 8)
            rows.extend(
                await semantic_search(self.session, repository.id, query, limit=repository_limit)
            )
        manual_limit = {"low": 3, "normal": 6, "deep": 12}.get(self.retrieval_depth, 6)
        manual = await search_agent_knowledge(self.session, role, query, limit=manual_limit)
        rows.extend(
            {
                "file_path": f"manual://{row['source_id']}",
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": row["score"],
            }
            for row in manual
        )
        unique: dict[tuple[str, int, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row["file_path"]), int(row["chunk_index"]), str(row["content"]))
            unique[key] = row
        return list(unique.values())

    async def _plan(self, task: Task) -> dict[str, Any] | None:
        thinker = await self.session.scalar(
            select(Job)
            .where(
                Job.task_id == task.id,
                Job.role == JobRole.THINKER,
                Job.result.is_not(None),
            )
            .order_by(Job.finished_at.desc())
        )
        return thinker.result if thinker else None

    async def _findings(self, task: Task) -> list[dict[str, Any]]:
        findings = list(
            (
                await self.session.scalars(
                    select(ReviewFinding)
                    .where(ReviewFinding.task_id == task.id, ReviewFinding.status == "OPEN")
                    .order_by(ReviewFinding.created_at)
                )
            ).all()
        )
        return [
            {
                "id": str(finding.id),
                "severity": finding.severity,
                "path": finding.file_path,
                "line": finding.line,
                "message": finding.message,
                "workspace_fingerprint": finding.workspace_fingerprint,
            }
            for finding in findings
        ]

    async def compile_for_intake(self, task: Task, job: Job) -> dict[str, Any]:
        started = time.monotonic()
        context = self._base(task, job)
        context["task_memory"] = await self._persistent_memory(task, JobRole.INTAKE)
        context["retrieved_knowledge"] = await self._knowledge(task, None, JobRole.INTAKE)
        return await self._finish(task, job, context, started)

    async def compile_for_thinker(
        self, task: Task, job: Job, repository: Repository | None
    ) -> dict[str, Any]:
        started = time.monotonic()
        context = self._base(task, job)
        context["task_memory"] = await self._persistent_memory(task, JobRole.THINKER)
        context["previous_role_checkpoint"] = await self._previous_checkpoint(task, JobRole.THINKER)
        context["retrieved_knowledge"] = await self._knowledge(task, repository, JobRole.THINKER)
        return await self._finish(task, job, context, started)

    async def compile_for_executor(
        self, task: Task, job: Job, repository: Repository, workspace: Path
    ) -> dict[str, Any]:
        started = time.monotonic()
        context = self._base(task, job)
        context["task_memory"] = await self._persistent_memory(task, JobRole.EXECUTOR)
        previous_checkpoint = await self._previous_checkpoint(task, JobRole.EXECUTOR)
        context["previous_role_checkpoint"] = previous_checkpoint
        context["technical_plan"] = await self._plan(task)
        context["retrieved_knowledge"] = await self._knowledge(task, repository, JobRole.EXECUTOR)
        context["open_findings"] = await self._findings(task)
        repository_data: dict[str, Any] = {
            "branch": task.branch_name,
            "revision": task.current_revision,
        }
        previous_sha = (
            previous_checkpoint.get("repository_sha")
            if isinstance(previous_checkpoint, dict)
            else None
        )
        if isinstance(previous_sha, str) and previous_sha:
            try:
                committed_delta = await run_git(
                    "diff", "--no-ext-diff", previous_sha, "HEAD", cwd=workspace
                )
                working_delta = await run_git("diff", "--no-ext-diff", cwd=workspace)
                repository_data["delta_from_previous_executor"] = {
                    "from_revision": previous_sha,
                    "content": "\n".join(filter(None, (committed_delta, working_delta))),
                }
                repository_data["context_mode"] = "delta"
            except RuntimeError:
                repository_data["files"] = await repository_context(workspace)
                repository_data["context_mode"] = "full_fallback"
        else:
            repository_data["files"] = await repository_context(workspace)
            repository_data["context_mode"] = "full"
        context["repository"] = repository_data
        return await self._finish(task, job, context, started)

    async def compile_for_reviewer(
        self, task: Task, job: Job, repository: Repository, workspace: Path
    ) -> dict[str, Any]:
        started = time.monotonic()
        context = self._base(task, job)
        context["task_memory"] = await self._persistent_memory(task, JobRole.REVIEWER)
        context["technical_plan"] = await self._plan(task)
        context["retrieved_knowledge"] = await self._knowledge(task, repository, JobRole.REVIEWER)
        context["open_findings"] = await self._findings(task)
        context["repository"] = {
            "branch": task.branch_name,
            "revision": task.current_revision,
            "diff": await run_git("diff", "--no-ext-diff", cwd=workspace),
        }
        return await self._finish(task, job, context, started)

    async def compile_for_tester(
        self,
        task: Task,
        job: Job,
        repository: Repository,
        workspace: Path,
        checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = time.monotonic()
        context = self._base(task, job)
        context["task_memory"] = await self._persistent_memory(task, JobRole.TESTER)
        context["technical_plan"] = await self._plan(task)
        context["open_findings"] = await self._findings(task)
        context["validation_results"] = checks
        context["repository"] = {
            "branch": task.branch_name,
            "revision": task.current_revision,
            "diff": await run_git("diff", "--no-ext-diff", cwd=workspace),
        }
        return await self._finish(task, job, context, started)
