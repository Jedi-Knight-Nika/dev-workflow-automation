from datetime import datetime, timedelta


def is_worker_online(
    *,
    status: str,
    last_heartbeat: datetime,
    now: datetime,
    heartbeat_seconds: float,
) -> bool:
    return status == "ONLINE" and last_heartbeat >= now - timedelta(seconds=heartbeat_seconds * 3)
