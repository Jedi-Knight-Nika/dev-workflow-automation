from uuid import uuid4

from app.agent_runtime.domain.request_usage import public_request_count, with_request_count
from app.intake.domain.ci import ci_observation


def test_request_counts_distinguish_unknown_zero_and_partial_without_billing_inference():
    assert public_request_count({"cost_usd": 0}) == {
        "request_count": None,
        "request_count_complete": False,
    }
    assert public_request_count({"inference_started": False}) == {
        "request_count": 0,
        "request_count_complete": True,
    }
    assert public_request_count(with_request_count({}, 3)) == {
        "request_count": 3,
        "request_count_complete": True,
    }
    assert (
        public_request_count(with_request_count({}, 2, complete=False))["request_count_complete"]
        is False
    )
    for invalid in (-1, True, "3", 1_000_001, 0.5):
        assert public_request_count({"request_count": invalid})["request_count"] is None


def test_ci_identity_deduplicates_status_notifications_without_leaking_names_or_urls():
    repository = uuid4()
    payload = {
        "sha": "a" * 40,
        "context": "private check name",
        "state": "failure",
        "id": 1,
        "target_url": "https://secret.test",
        "description": "private output",
    }
    failed = ci_observation(repository, "status", payload)
    passed = ci_observation(repository, "status", {**payload, "id": 2, "state": "success"})
    assert failed and passed and failed["check_key"] == passed["check_key"]
    assert (
        failed["status"] == "FAILURE"
        and "private" not in str(failed)
        and "secret" not in str(failed)
    )
    assert ci_observation(repository, "status", {**payload, "sha": "invalid"}) is None
    assert (
        ci_observation(repository, "status", {**payload, "state": "private"})["status"] == "UNKNOWN"
    )
    run = {"check_run": {"head_sha": "a" * 40, "id": 1, "conclusion": "failure"}}
    rerun = {"check_run": {**run["check_run"], "id": 2}}
    assert (
        ci_observation(repository, "check_run", run)["check_key"]
        != ci_observation(repository, "check_run", rerun)["check_key"]
    )
