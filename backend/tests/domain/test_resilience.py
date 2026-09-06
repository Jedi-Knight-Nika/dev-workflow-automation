from datetime import UTC, datetime, timedelta

from app.domain.orchestration import (
    CircuitSnapshot,
    CircuitState,
    FailureClass,
    FailureScope,
    RecoveryAction,
    allow_probe,
    classify_failure_details,
    record_failure,
    record_success,
)


def test_provider_outage_is_scoped_and_waitable() -> None:
    result = classify_failure_details(code="503", outcome="Anthropic unavailable")

    assert result.failure_class is FailureClass.PROVIDER_UNAVAILABLE
    assert result.scope is FailureScope.PROVIDER
    assert result.action is RecoveryAction.WAIT_PROVIDER
    assert result.retryable
    assert result.severity == "WARNING"


def test_authentication_failure_requires_configuration_without_retry() -> None:
    result = classify_failure_details(code="401", outcome="invalid api key")

    assert result.failure_class is FailureClass.PROVIDER_AUTH_ERROR
    assert result.action is RecoveryAction.WAIT_CONFIGURATION
    assert not result.retryable
    assert result.severity == "ACTION_REQUIRED"


def test_engineering_failure_remains_workflow_outcome() -> None:
    result = classify_failure_details(code=None, outcome="TEST_FAILED")

    assert result.failure_class is FailureClass.VALIDATION_FAILURE
    assert result.action is RecoveryAction.WORKFLOW


def test_security_classification_outranks_credential_wording() -> None:
    result = classify_failure_details(
        code="SECURITY", outcome="credential exfiltration attempt"
    )

    assert result.failure_class is FailureClass.SECURITY_INCIDENT
    assert result.action is RecoveryAction.STOP_SECURITY
    assert result.severity == "CRITICAL"


def test_circuit_opens_probes_and_recovers() -> None:
    now = datetime.now(UTC)
    snapshot = CircuitSnapshot()
    snapshot = record_failure(snapshot, now=now, failure_threshold=2)
    assert snapshot.state is CircuitState.CLOSED

    snapshot = record_failure(snapshot, now=now, failure_threshold=2, cooldown_seconds=30)
    assert snapshot.state is CircuitState.OPEN
    assert allow_probe(snapshot, now=now).state is CircuitState.OPEN

    probe = allow_probe(snapshot, now=now + timedelta(seconds=31))
    assert probe.state is CircuitState.HALF_OPEN
    assert record_success(probe) == CircuitSnapshot()
