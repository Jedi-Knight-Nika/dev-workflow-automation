import base64
import binascii
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from uuid import UUID

from app.engineering.application.ports.task_queries import TaskListFilters, TaskView


@dataclass(frozen=True)
class TaskCursor:
    value: int | datetime | None
    created_at: datetime
    task_id: UUID


def filter_key(filters: TaskListFilters) -> str:
    values = asdict(filters)
    values.pop("cursor")
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def next_cursor(view: TaskView, filters: TaskListFilters) -> str:
    value = {
        "priority": view.task.priority,
        "created": view.task.created_at,
        "updated": view.task.updated_at,
        "due": view.task.due_at,
    }[filters.sort]
    payload = {
        "version": 1,
        "filters": filter_key(filters),
        "value": value,
        "created_at": view.task.created_at.isoformat(),
        "task_id": str(view.task.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).decode()


def read_cursor(filters: TaskListFilters) -> TaskCursor | None:
    if not filters.cursor:
        return None
    try:
        if len(filters.cursor) > 2048:
            raise ValueError
        payload = json.loads(base64.b64decode(filters.cursor, altchars=b"-_", validate=True))
        if not isinstance(payload, dict):
            raise TypeError
        if payload["version"] != 1 or payload["filters"] != filter_key(filters):
            raise ValueError
        if not isinstance(payload["task_id"], str):
            raise TypeError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        value = payload["value"]
        if filters.sort == "priority":
            if type(value) is not int or not 0 <= value <= 5:
                raise ValueError
        elif value is not None:
            value = datetime.fromisoformat(value)
            if value.tzinfo is None:
                raise ValueError
        elif filters.sort != "due":
            raise ValueError
        return TaskCursor(value, created_at, UUID(payload["task_id"]))
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise ValueError("Invalid task cursor; reload the task list") from exc
