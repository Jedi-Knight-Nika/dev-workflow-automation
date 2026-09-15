"""Translate service failures at the HTTP boundary, preserving their public detail."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException


@contextmanager
def service_errors() -> Iterator[None]:
    """Use only for endpoints whose contract maps missing/conflicting state to 404/409."""
    try:
        yield
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
