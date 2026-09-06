import pytest

from app.domain.webhooks import DeliveryRetryPolicy


def test_delivery_retry_policy_exhaustion_boundary() -> None:
    policy = DeliveryRetryPolicy(max_attempts=3)

    assert not policy.exhausted(2)
    assert policy.exhausted(3)


def test_delivery_retry_policy_bounds_persisted_error() -> None:
    policy = DeliveryRetryPolicy(max_error_chars=8)

    assert policy.error_message(RuntimeError("sensitive failure")) == "sensitiv"


@pytest.mark.parametrize("field", ["max_attempts", "max_error_chars"])
def test_delivery_retry_policy_rejects_invalid_limits(field: str) -> None:
    arguments = {field: 0}
    with pytest.raises(ValueError, match=f"{field} must be positive"):
        DeliveryRetryPolicy(**arguments)  # type: ignore[arg-type]
