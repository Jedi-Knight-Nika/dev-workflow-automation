"""Translate service failures at the HTTP boundary, preserving their public detail."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException


@contextmanager
def service_errors(*, value_status: int = 409) -> Iterator[None]:
    """Missing state is 404; callers may select the status for invalid input."""
    try:
        yield
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(value_status, str(exc)) from exc
