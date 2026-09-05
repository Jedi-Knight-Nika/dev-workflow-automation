from app.domain.jobs import RetryPolicy


def test_retry_delay_uses_exponential_backoff() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=5)

    assert [policy.delay_seconds(attempt) for attempt in (1, 2, 3)] == [5, 10, 20]
    assert policy.should_retry(2)
    assert not policy.should_retry(3)
