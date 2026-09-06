from app.domain.orchestration import (
    FailureClass,
    ProgressFingerprint,
    StrategyKind,
    TaskProfiler,
    ValidationEvidence,
    classify_failure,
    evidence_is_current,
    progress_made,
    resolve_execution_strategy,
)


def test_low_risk_task_uses_fast_bounded_strategy() -> None:
    profile = TaskProfiler().profile(
        title="Fix button label", description="Correct a typo in settings.", labels=[]
    )
    strategy = resolve_execution_strategy(profile)

    assert strategy.kind == StrategyKind.FAST
    assert strategy.max_job_turns == 10
    assert not strategy.allow_parallel_specialists


def test_critical_domain_requires_human_gate() -> None:
    profile = TaskProfiler().profile(
        title="Change production payment permissions", description="", labels=[]
    )
    strategy = resolve_execution_strategy(profile)

    assert strategy.kind == StrategyKind.HIGH_ASSURANCE
    assert strategy.require_human_gate


def test_parallel_strategy_requires_explicit_independent_signal() -> None:
    profile = TaskProfiler().profile(
        title="Cross-service architecture research",
        description="Investigate independent changes across multiple services.",
        labels=[],
    )

    assert resolve_execution_strategy(profile).kind == StrategyKind.PARALLEL_INVESTIGATION


def test_progress_requires_changed_evidence() -> None:
    before = ProgressFingerprint("abc", "plan-1", ("test-a",), ("finding-a",), "files-1", "FAIL")
    same = ProgressFingerprint("abc", "plan-1", ("test-a",), ("finding-a",), "files-1", "FAIL")
    improved = ProgressFingerprint("abc", "plan-1", (), ("finding-a",), "files-1", "FAIL")

    assert not progress_made(before, same)
    assert progress_made(before, improved)


def test_failure_classification_keeps_infrastructure_out_of_rework() -> None:
    assert (
        classify_failure(code="PROVIDER_RATE_LIMIT", outcome=None)
        == FailureClass.PROVIDER_RATE_LIMIT
    )
    assert classify_failure(code=None, outcome="TEST_FAILED") == FailureClass.VALIDATION_FAILURE
    assert classify_failure(code="POLICY_DENIED", outcome=None) == FailureClass.POLICY_DENIED


def test_validation_evidence_is_bound_to_sha_and_configuration() -> None:
    evidence = ValidationEvidence("abc", "pytest-v1", "PASSED")

    assert evidence_is_current(evidence, repository_sha="abc", configuration_hash="pytest-v1")
    assert not evidence_is_current(evidence, repository_sha="def", configuration_hash="pytest-v1")
