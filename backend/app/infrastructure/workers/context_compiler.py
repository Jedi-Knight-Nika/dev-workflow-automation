import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IndexStatus, Job, JobRole, Repository, ReviewFinding, Task
from app.infrastructure.git.workspaces import run_git
from app.infrastructure.indexing import semantic_search
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
    def __init__(self, session: AsyncSession, max_chars: int = DEFAULT_CONTEXT_CHARS) -> None:
        self.session = session
        self.max_chars = max_chars

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

    async def _knowledge(self, task: Task, repository: Repository | None) -> list[dict[str, Any]]:
        if repository is None or repository.index_status != IndexStatus.READY:
            return []
        rows = await semantic_search(
            self.session, repository.id, f"{task.title}\n{task.description}", limit=8
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
        return fit_context(self._base(task, job), self.max_chars)

    async def compile_for_thinker(
        self, task: Task, job: Job, repository: Repository | None
    ) -> dict[str, Any]:
        context = self._base(task, job)
        context["retrieved_knowledge"] = await self._knowledge(task, repository)
        return fit_context(context, self.max_chars)

    async def compile_for_executor(
        self, task: Task, job: Job, repository: Repository, workspace: Path
    ) -> dict[str, Any]:
        context = self._base(task, job)
        context["technical_plan"] = await self._plan(task)
        context["retrieved_knowledge"] = await self._knowledge(task, repository)
        context["open_findings"] = await self._findings(task)
        context["repository"] = {
            "branch": task.branch_name,
            "revision": task.current_revision,
            "files": await repository_context(workspace),
        }
        return fit_context(context, self.max_chars)

    async def compile_for_reviewer(
        self, task: Task, job: Job, repository: Repository, workspace: Path
    ) -> dict[str, Any]:
        context = self._base(task, job)
        context["technical_plan"] = await self._plan(task)
        context["open_findings"] = await self._findings(task)
        context["repository"] = {
            "branch": task.branch_name,
            "revision": task.current_revision,
            "diff": await run_git("diff", "--no-ext-diff", cwd=workspace),
        }
        return fit_context(context, self.max_chars)
