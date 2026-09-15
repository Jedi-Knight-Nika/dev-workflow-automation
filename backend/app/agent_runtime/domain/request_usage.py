"""Recorded provider request attempts, independent of token/cost completeness."""

from typing import Any


def with_request_count(raw: dict[str, Any], count: int, *, complete: bool = True) -> dict[str, Any]:
    return {**raw, "request_count": count, "request_count_complete": complete}


def public_request_count(raw: object) -> dict[str, int | bool | None]:
    value = raw if isinstance(raw, dict) else {}
    if value.get("inference_started") is False:
        return {"request_count": 0, "request_count_complete": True}
    count = value.get("request_count")
    if type(count) is not int or not 0 <= count <= 1_000_000:
        return {"request_count": None, "request_count_complete": False}
    return {
        "request_count": count,
        "request_count_complete": value.get("request_count_complete") is True,
    }
