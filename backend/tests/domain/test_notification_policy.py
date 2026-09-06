import pytest

from app.domain.notifications import NotificationSeverity, telegram_required


@pytest.mark.parametrize(
    "severity", [NotificationSeverity.ACTION_REQUIRED, NotificationSeverity.CRITICAL]
)
def test_actionable_notifications_route_to_telegram(severity: NotificationSeverity) -> None:
    assert telegram_required(severity)


@pytest.mark.parametrize("severity", [NotificationSeverity.INFO, NotificationSeverity.WARNING])
def test_routine_notifications_stay_in_app(severity: NotificationSeverity) -> None:
    assert not telegram_required(severity)
