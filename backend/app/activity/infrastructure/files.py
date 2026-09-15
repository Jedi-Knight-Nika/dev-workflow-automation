"""Best-effort metadata from immutable commits, using a read-only workspace mount."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.activity.domain.events import file_path, reference
from app.activity.infrastructure.models import ActivityEvent, ActivityFileChange
from app.activity.infrastructure.projector import PROJECTION_LOCK
from app.agent_runtime.infrastructure.process import capture
from app.engineering.infrastructure.task_models import Task, TaskRepositoryScope


class FileHistoryError(ValueError):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def parse_changes(status: bytes, stats: bytes) -> list[dict[str, Any]]:
    """Parse NUL-delimited Git output; renames and binary sizes stay explicit."""
    sizes: dict[str, tuple[int | None, int | None]] = {}
    fields = iter(stats.decode("utf-8", errors="replace").split("\0"))
    for entry in fields:
        if not entry:
            continue
        added, deleted, path = entry.split("\t", 2)
        if not path:  # Git's rename form has two additional NUL-delimited paths.
            next(fields)
            path = next(fields)
        sizes[path] = (
            int(added) if added != "-" else None,
            int(deleted) if deleted != "-" else None,
        )
    tokens = iter(status.decode("utf-8", errors="replace").split("\0"))
    result: list[dict[str, Any]] = []
    for operation in tokens:
        if not operation:
            continue
        before = next(tokens)
        previous = before if operation.startswith("R") else None
        path = next(tokens) if previous else before
        if (
            operation[0] not in {"A", "M", "D", "R", "T"}
            or not file_path(path)
            or (previous and not file_path(previous))
        ):
            continue
        added_lines, deleted_lines = sizes.get(path, (None, None))
        result.append(
            {
                "operation": "M" if operation[0] == "T" else operation[0],
                "path": path,
                "previous_path": previous,
                "lines_added": added_lines,
                "lines_deleted": deleted_lines,
            }
        )
        if len(result) > 200:
            raise FileHistoryError("TOO_LARGE")
    return result


async def committed_changes(workspace: Path, root: Path, revision: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise ValueError("Invalid commit identity")
    path = workspace.resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Workspace is outside the configured root")

    async def git(option: str) -> bytes:
        return await capture(
            [
                "git",
                "-c",
                "safe.directory=" + str(path),
                "-c",
                "core.hooksPath=/dev/null",
                "--no-optional-locks",
                "show",
                "--format=",
                "--no-ext-diff",
                "--no-textconv",
                "--find-renames",
                option,
                "-z",
                revision,
                "--",
            ],
            cwd=path,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=3,
            output_limit=256_000,
        )

    return parse_changes(await git("--name-status"), await git("--numstat"))


async def collect_files(sessions: async_sessionmaker[AsyncSession], root: Path) -> None:
    # One immutable revision per iteration; failures retry after a minute and
    # never prevent other milestones from being projected.
    async with sessions() as session, session.begin():
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": PROJECTION_LOCK}
        ):
            return
        event = await session.scalar(
            select(ActivityEvent)
            .where(
                ActivityEvent.kind == "VALIDATION_PASSED",
                ActivityEvent.payload["head_sha"].astext.is_not(None),
                or_(
                    ActivityEvent.file_retry_at.is_(None),
                    ActivityEvent.file_retry_at <= datetime.now(UTC),
                ),
                or_(
                    ActivityEvent.file_status.is_(None),
                    ActivityEvent.file_status.not_in(
                        ["COMPLETE", "TOO_LARGE", "INVALID", "EXPIRED"]
                    ),
                ),
            )
            .order_by(ActivityEvent.file_retry_at.asc().nullsfirst(), ActivityEvent.sequence)
            .limit(1)
        )
        if event is None:
            return
        event.file_checked_at = datetime.now(UTC)
        event.file_attempts += 1
        event.file_retry_at = datetime.now(UTC) + timedelta(
            seconds=min(3600, 60 * 2 ** min(event.file_attempts - 1, 6))
        )
        event.file_status = "UNAVAILABLE"
        task = await session.get(Task, event.task_id)
        if task is None:
            return
        revision = str(event.payload["head_sha"])
        identity = f"{task.id}:{revision}"
        existing = await session.scalar(
            select(ActivityEvent).where(
                ActivityEvent.source_type == "code", ActivityEvent.source_id == identity
            )
        )
        if existing:
            # This source is complete; keep it out of the retry queue.
            event.file_status, event.file_retry_at = existing.file_status or "COMPLETE", None
            return
        scope = await session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.task_id == task.id,
                TaskRepositoryScope.is_primary.is_(True),
            )
        )
        repository_id = scope.repository_id if scope else task.repository_id
        workspace = scope.workspace_path if scope else task.workspace_path
        if not workspace or not repository_id:
            event.file_status = "MISSING_WORKSPACE"
            return
        try:
            files = await committed_changes(Path(workspace), root, revision)
        except FileHistoryError as exc:
            event.file_status, event.file_retry_at = exc.status, None
            return
        except RuntimeError as exc:
            if str(exc) == "Operation exceeded its output bound":
                event.file_status, event.file_retry_at = "TOO_LARGE", None
            return
        except ValueError:
            event.file_status, event.file_retry_at = "INVALID", None
            return
        except (OSError, StopIteration):
            return
        code = ActivityEvent(
            task_id=task.id,
            source_type="code",
            source_id=identity,
            kind="CODE_CHANGED",
            detail_level=2,
            actor_type="system",
            actor="Validated commit",
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id,
            payload={
                "head_sha": revision,
                "repository_id": str(repository_id),
                "file_count": len(files),
                "lines_added": sum(item["lines_added"] or 0 for item in files),
                "lines_deleted": sum(item["lines_deleted"] or 0 for item in files),
                "unknown_line_counts": sum(item["lines_added"] is None for item in files),
            },
            references=[reference(event.source_type, event.source_id, "validated_commit")],
            file_status="COMPLETE",
        )
        session.add(code)
        await session.flush()
        for item in files:
            session.add(
                ActivityFileChange(
                    event_sequence=code.sequence, repository_id=repository_id, **item
                )
            )
        event.file_status, event.file_retry_at = "COMPLETE", None
