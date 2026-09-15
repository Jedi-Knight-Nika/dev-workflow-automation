"""Provider settings validation without persistence or network dependencies."""

from typing import Any


def merge_configuration(
    provider: str, current: dict[str, Any], changes: dict[str, Any]
) -> dict[str, Any]:
    values = {**current, **changes}
    for key in ("actor_ids", "source_state_ids", "list_ids"):
        if key in values and (
            not isinstance(values[key], list)
            or len(values[key]) > 200
            or any(not isinstance(item, str) or not item.strip() for item in values[key])
        ):
            raise ValueError(f"{key} must be a list of at most 200 nonempty IDs")
    if provider == "trello" and "poll_interval_seconds" in values:
        interval = values["poll_interval_seconds"]
        if type(interval) is not int or not 15 <= interval <= 3600:
            raise ValueError("Trello polling interval must be 15–3600 seconds")
    return values
