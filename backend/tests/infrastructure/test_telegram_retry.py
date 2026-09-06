import httpx

from app.infrastructure.telegram import telegram_retry_delay


def test_telegram_retry_delay_prefers_api_parameter() -> None:
    response = httpx.Response(429, json={"parameters": {"retry_after": 45}})

    assert telegram_retry_delay(response, 1) == 45


def test_telegram_retry_delay_uses_header_then_bounded_backoff() -> None:
    assert telegram_retry_delay(httpx.Response(429, headers={"retry-after": "12"}), 1) == 12
    assert telegram_retry_delay(httpx.Response(503), 10) == 300
