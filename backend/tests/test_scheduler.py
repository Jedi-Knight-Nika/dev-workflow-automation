from app.services.scheduler import retry_delay


def test_retry_delay_uses_exponential_backoff() -> None:
    assert [retry_delay(5, attempt) for attempt in (1, 2, 3)] == [5, 10, 20]
