import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentCheckpoint, Job, JobContext, ReviewFinding, Task, TaskMemory
from app.domain.memory import MemorySnapshot, checkpoint_payload
from app.domain.operational_states import JobRole


class TaskMemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, task: Task) -> MemorySnapshot:
        record = await self._session.get(TaskMemory, task.id)
        if record is None:
            record = TaskMemory(task_id=task.id, goal=task.title, current_sha=task.current_revision)
            self._session.add(record)
            await self._session.flush()
        return self._snapshot(record)

    async def latest_checkpoint(self, task_id: uuid.UUID, role: JobRole) -> AgentCheckpoint | None:
        checkpoint: AgentCheckpoint | None = await self._session.scalar(
            select(AgentCheckpoint)
            .where(AgentCheckpoint.task_id == task_id, AgentCheckpoint.role == role)
            .order_by(AgentCheckpoint.created_at.desc())
        )
        return checkpoint

    async def checkpoint(
        self,
        task: Task,
        job: Job,
        result: dict[str, object],
        summary: str,
        agent_id: uuid.UUID | None,
        role_id: uuid.UUID | None,
    ) -> None:
        existing = await self._session.scalar(
            select(AgentCheckpoint.id).where(AgentCheckpoint.job_id == job.id)
        )
        if existing is not None:
            return
        structured = checkpoint_payload(job.role, result)
        self._session.add(
            AgentCheckpoint(
                task_id=task.id,
                job_id=job.id,
                agent_id=agent_id,
                role_id=role_id,
                role=job.role,
                checkpoint_type=f"{job.role.value}_RESULT",
                repository_sha=task.current_revision,
                summary=summary[:4000],
                structured_data=structured,
                token_estimate=max(1, len(json.dumps(structured)) // 4),
            )
        )
        memory = await self._record(task)
        memory.goal = str(result.get("goal") or memory.goal or task.title)[:4000]
        memory.current_sha = (
            str(result.get("workspace_revision") or task.current_revision or "") or None
        )
        if job.role == JobRole.THINKER:
            memory.current_plan_job_id = (
                job.id if result.get("result") == "PLAN_READY" else memory.current_plan_job_id
            )
            memory.decisions = self._merged(memory.decisions, structured.get("decisions"))
            memory.important_files = self._merged(
                memory.important_files, structured.get("important_files")
            )
            memory.open_questions = self._strings(structured.get("open_questions"))
        elif job.role == JobRole.EXECUTOR:
            memory.important_files = self._merged(
                memory.important_files, structured.get("important_files")
            )
        memory.open_finding_ids = [
            str(value)
            for value in (
                await self._session.scalars(
                    select(ReviewFinding.id).where(
                        ReviewFinding.task_id == task.id, ReviewFinding.status == "OPEN"
                    )
                )
            ).all()
        ]
        memory.version += 1
        await self._session.commit()

    async def record_context(
        self,
        job: Job,
        memory_version: int | None,
        repository_sha: str | None,
        checkpoint_ids: list[str],
        plan_job_id: uuid.UUID | None,
        finding_ids: list[str],
        rag_chunk_ids: list[str],
        estimated_tokens: int,
        duration_ms: int,
    ) -> None:
        existing = await self._session.scalar(
            select(JobContext.id).where(JobContext.job_id == job.id)
        )
        if existing is None:
            self._session.add(
                JobContext(
                    job_id=job.id,
                    compiler_version="v1",
                    task_memory_version=memory_version,
                    repository_sha=repository_sha,
                    checkpoint_ids=checkpoint_ids,
                    plan_job_id=plan_job_id,
                    finding_ids=finding_ids,
                    rag_chunk_ids=rag_chunk_ids,
                    estimated_input_tokens=estimated_tokens,
                    compilation_duration_ms=duration_ms,
                )
            )
            await self._session.commit()

    async def _record(self, task: Task) -> TaskMemory:
        record = await self._session.get(TaskMemory, task.id)
        if record is None:
            record = TaskMemory(task_id=task.id, goal=task.title, current_sha=task.current_revision)
            self._session.add(record)
            await self._session.flush()
        return record

    @staticmethod
    def _merged(existing: list[str], incoming: object, limit: int = 100) -> list[str]:
        return list(dict.fromkeys([*existing, *TaskMemoryService._strings(incoming)]))[-limit:]

    @staticmethod
    def _strings(value: object) -> list[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _snapshot(record: TaskMemory) -> MemorySnapshot:
        return MemorySnapshot(
            record.goal,
            tuple(record.known_facts),
            tuple(record.decisions),
            tuple(record.rejected_approaches),
            tuple(record.invariants),
            tuple(record.important_files),
            tuple(record.important_symbols),
            tuple(record.open_questions),
            tuple(record.open_finding_ids),
            tuple(record.resolved_finding_summaries),
            str(record.current_plan_job_id) if record.current_plan_job_id else None,
            record.current_sha,
            record.version,
        )


class SqlAlchemyTaskMemoryQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def memory(self, task_id: uuid.UUID) -> dict[str, object]:
        record = await self._session.get(TaskMemory, task_id)
        if record is None:
            task = await self._session.get(Task, task_id)
            if task is None:
                raise LookupError("Task not found")
            snapshot = await TaskMemoryService(self._session).load(task)
        else:
            snapshot = TaskMemoryService._snapshot(record)
        return {
            "task_id": task_id,
            "goal": snapshot.goal,
            "known_facts": list(snapshot.known_facts),
            "decisions": list(snapshot.decisions),
            "rejected_approaches": list(snapshot.rejected_approaches),
            "invariants": list(snapshot.invariants),
            "important_files": list(snapshot.important_files),
            "important_symbols": list(snapshot.important_symbols),
            "open_questions": list(snapshot.open_questions),
            "open_finding_ids": list(snapshot.open_finding_ids),
            "resolved_finding_summaries": list(snapshot.resolved_finding_summaries),
            "current_plan_job_id": snapshot.current_plan_job_id,
            "current_sha": snapshot.current_sha,
            "version": snapshot.version,
        }

    async def checkpoints(self, task_id: uuid.UUID) -> list[dict[str, object]]:
        records = (
            await self._session.scalars(
                select(AgentCheckpoint)
                .where(AgentCheckpoint.task_id == task_id)
                .order_by(AgentCheckpoint.created_at.desc())
            )
        ).all()
        return [
            {
                "id": item.id,
                "job_id": item.job_id,
                "role": item.role.value,
                "repository_sha": item.repository_sha,
                "summary": item.summary,
                "structured_data": item.structured_data,
                "token_estimate": item.token_estimate,
                "created_at": item.created_at,
            }
            for item in records
        ]

    async def contexts(self, task_id: uuid.UUID) -> list[dict[str, object]]:
        records = (
            await self._session.scalars(
                select(JobContext)
                .join(Job, Job.id == JobContext.job_id)
                .where(Job.task_id == task_id)
                .order_by(JobContext.created_at.desc())
            )
        ).all()
        return [self._context(item) for item in records]

    async def job_context(self, job_id: uuid.UUID) -> dict[str, object]:
        record = await self._session.scalar(select(JobContext).where(JobContext.job_id == job_id))
        if record is None:
            raise LookupError("Job context not found")
        return self._context(record)

    @staticmethod
    def _context(item: JobContext) -> dict[str, object]:
        return {
            "id": item.id,
            "job_id": item.job_id,
            "compiler_version": item.compiler_version,
            "task_memory_version": item.task_memory_version,
            "repository_sha": item.repository_sha,
            "checkpoint_ids": item.checkpoint_ids,
            "plan_job_id": item.plan_job_id,
            "finding_ids": item.finding_ids,
            "rag_chunk_ids": item.rag_chunk_ids,
            "estimated_input_tokens": item.estimated_input_tokens,
            "compilation_duration_ms": item.compilation_duration_ms,
            "created_at": item.created_at,
        }
