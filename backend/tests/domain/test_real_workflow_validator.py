import sys

import pytest
from scripts import validate_real_workflow as observer


@pytest.mark.parametrize("status,exit_code", [("MERGED", 0), ("PAUSED", 2), ("WAITING_HUMAN", 2)])
def test_observer_only_reads_and_does_not_retry_or_merge(monkeypatch, capsys, status, exit_code):
    calls = []
    task = {
        "id": "task-1",
        "external_key": "TRELLO-test",
        "status": status,
        "stage": "DEVELOPING",
        "wait_reason": "NONE",
    }

    def request(base_url, path):
        calls.append(path)
        return [task] if path.startswith("/tasks?") else []

    monkeypatch.setattr(observer, "request", request)
    monkeypatch.setattr(sys, "argv", ["observe", "TRELLO-test"])
    assert observer.main() == exit_code
    assert len(calls) == 5
    assert all(not path.endswith(("/resume", "/merge")) for path in calls)
    assert status in capsys.readouterr().out
