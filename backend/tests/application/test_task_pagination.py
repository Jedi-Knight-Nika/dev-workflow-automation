import base64
import json
from dataclasses import replace

import pytest

from app.engineering.application.ports.task_queries import TaskListFilters
from app.engineering.application.task_pagination import filter_key, read_cursor


@pytest.mark.parametrize("cursor", ["!bad", "bnVsbA==", "e30=", "W10=", "x" * 2049])
def test_invalid_cursors_are_public_validation_errors(cursor):
    with pytest.raises(ValueError, match="Invalid task cursor"):
        read_cursor(replace(TaskListFilters(), cursor=cursor))


@pytest.mark.parametrize("task_id", [None, 42, [], {}])
def test_invalid_cursor_identity_is_a_public_validation_error(task_id):
    filters = TaskListFilters()
    payload = {
        "version": 1,
        "filters": filter_key(filters),
        "value": 3,
        "created_at": "2026-01-01T00:00:00+00:00",
        "task_id": task_id,
    }
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(ValueError, match="Invalid task cursor"):
        read_cursor(replace(filters, cursor=cursor))
