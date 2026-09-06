from scripts.validate_real_workflow import validate_history


def test_real_workflow_rejects_stale_checks_and_open_findings() -> None:
    jobs = [
        {"role": role, "state": "SUCCEEDED"}
        for role in ("INTAKE", "THINKER", "EXECUTOR", "REVIEWER")
    ]
    problems = validate_history(
        {
            "state": "READY_TO_MERGE",
            "current_revision": "new-sha",
        },
        jobs,
        [
            {"event_type": "PULL_REQUEST_CREATED"},
            {"event_type": "TASK_READY_TO_MERGE"},
        ],
        [{"kind": "CHECK", "name": "CI", "status": "SUCCESS", "revision": "old-sha"}],
        [{"status": "OPEN"}],
        False,
    )

    assert "no GitHub check evidence for current revision" in problems
    assert "unresolved internal review findings remain" in problems


def test_real_workflow_accepts_current_clean_revision() -> None:
    jobs = [
        {"role": role, "state": "SUCCEEDED"}
        for role in ("INTAKE", "THINKER", "EXECUTOR", "REVIEWER")
    ]
    problems = validate_history(
        {"state": "READY_TO_MERGE", "current_revision": "head-sha"},
        jobs,
        [
            {"event_type": "PULL_REQUEST_CREATED"},
            {"event_type": "TASK_READY_TO_MERGE"},
        ],
        [{"kind": "CHECK", "name": "CI", "status": "SUCCESS", "revision": "head-sha"}],
        [{"status": "RESOLVED"}],
        False,
    )

    assert problems == []


def test_merged_workflow_validates_the_pre_merge_gate_revision() -> None:
    jobs = [
        {"role": role, "state": "SUCCEEDED"}
        for role in ("INTAKE", "THINKER", "EXECUTOR", "REVIEWER")
    ]
    problems = validate_history(
        {"state": "MERGED", "current_revision": "squash-merge-sha"},
        jobs,
        [
            {"event_type": "PULL_REQUEST_CREATED", "payload": {}},
            {"event_type": "TASK_READY_TO_MERGE", "payload": {"revision": "pr-head-sha"}},
        ],
        [
            {
                "kind": "CHECK",
                "name": "CI",
                "status": "SUCCESS",
                "revision": "pr-head-sha",
            }
        ],
        [],
        False,
    )

    assert problems == []
