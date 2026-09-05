from enum import StrEnum


class NotificationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    CRITICAL = "CRITICAL"


class NotificationStatus(StrEnum):
    UNREAD = "UNREAD"
    READ = "READ"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    MUTED = "MUTED"


def telegram_required(severity: NotificationSeverity) -> bool:
    return severity in {
        NotificationSeverity.ACTION_REQUIRED,
        NotificationSeverity.CRITICAL,
    }
