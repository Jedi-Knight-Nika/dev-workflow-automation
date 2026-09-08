"""Operator-console routes. Production ingress authentication applies unchanged."""

import asyncio
import hashlib
import json
import re
import secrets
import unicodedata
from collections.abc import AsyncIterator
from datetime import datetime
from time import monotonic
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.bootstrap.observer import get_observer, observer_runtime
from app.observability.observer.application import Observer
from app.observability.observer.domain import Scope, capacity_reason, number
from app.observability.observer.local_model import INSTALL_MODELS, OllamaObserver, local_model_name
from app.platform.configuration.settings import get_settings


async def enabled_observer() -> Observer:
    if not get_settings().observer_enabled or not observer_runtime.enabled:
        raise HTTPException(404, "Observer is disabled")
    # Streams register their own task below. Cancelling both an ASGI parent
    # request and its stream child can repeatedly interrupt database cleanup.
    # Short read-only requests may drain; no new work is admitted after off.
    return get_observer()


def owner(request: Request, response: Response) -> str:
    # Isolates browser conversations under the existing single-operator console.
    # This cookie is not authentication and is never used for engineering access.
    token = request.cookies.get("observer_browser", "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        token = secrets.token_hex(32)
        response.set_cookie(
            "observer_browser",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=2592000,
            path="/api/observer",
        )
    return hashlib.sha256(token.encode()).hexdigest()


class PageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: Literal["DASHBOARD", "TASK", "TEAM"] = "DASHBOARD"
    task_id: UUID | None = None
    team_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "PageContext":
        if self.page == "TASK" and (not self.task_id or self.team_id):
            raise ValueError("Task context requires only a task ID")
        if self.page == "TEAM" and (not self.team_id or self.task_id):
            raise ValueError("Team context requires only a team ID")
        if self.page == "DASHBOARD" and (self.task_id or self.team_id):
            raise ValueError("Dashboard context cannot contain scope IDs")
        return self

    def scope(self) -> Scope:
        return Scope(
            self.page,
            str(self.task_id) if self.task_id else None,
            str(self.team_id) if self.team_id else None,
        )


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    context: PageContext = Field(default_factory=PageContext)


class SnoozeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutes: Literal[15, 60, 1440] = 15


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus: Literal["normal", "warnings-only", "critical-only", "silent"] | None = None
    last_seen_at: datetime | None = None


router = APIRouter(prefix="/observer", tags=["observer"])


class ConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    enabled: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    local_ai_enabled: bool | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100)
    memory_reserve_mb: int | None = Field(default=None, ge=512, le=1048576)
    output_tokens: int | None = Field(default=None, ge=128, le=768)
    response_timeout_seconds: int | None = Field(default=None, ge=10, le=60)

    @model_validator(mode="after")
    def validate_changes(self) -> "ConfigurationInput":
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Provide a configuration change; null is not a setting")
        if self.model is not None and not local_model_name(self.model):
            raise ValueError("Only local Ollama model tags are allowed")
        if self.display_name and any(
            unicodedata.category(char).startswith("C") for char in self.display_name
        ):
            raise ValueError("The assistant name cannot contain control characters")
        return self


@router.get("/configuration")
async def configuration() -> dict[str, object]:
    return await observer_runtime.configure()


@router.put("/configuration")
async def save_configuration(body: ConfigurationInput) -> dict[str, object]:
    return await observer_runtime.configure(body.model_dump(exclude_unset=True))


@router.get("/models")
async def local_models() -> dict[str, Any]:
    settings = get_settings()
    model = OllamaObserver(settings.ollama_base_url, settings.observer_model)
    return {
        **await model.models(),
        "catalog": [
            {"name": name, "minimum_free_disk_mb": size} for name, size in INSTALL_MODELS.items()
        ],
    }


class ModelInstallInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:4b"]


@router.post("/models/install")
async def install_model(
    body: ModelInstallInput, request: Request, observer: Observer = Depends(enabled_observer)
) -> StreamingResponse:
    snapshot = await observer.reads.snapshot(Scope(), fresh=True)
    reason = capacity_reason(snapshot, True, 512)
    free = number(snapshot.host.get("host_disk_available"))
    if reason or free is None or free < INSTALL_MODELS[body.model] * 1048576:
        raise HTTPException(
            409,
            reason
            or "Not enough verified free disk for this download. Choose a smaller model or free disk space.",
        )
    if observer_runtime.installing:
        raise HTTPException(409, "A local model download is already running")

    async def stream() -> AsyncIterator[str]:
        if observer_runtime.installing or not observer_runtime.enabled:
            yield (
                "data: "
                + json.dumps({"error": "Model setup is busy or Jarvis was disabled."})
                + "\n\n"
            )
            return
        observer_runtime.installing = True
        observer.installing = True
        task = asyncio.current_task()
        if task:
            observer_runtime.active.add(task)
        checked = 0.0
        try:
            adapter = OllamaObserver(get_settings().ollama_base_url, body.model)
            async with asyncio.timeout(1800):
                async for progress in adapter.install(body.model):
                    if await request.is_disconnected():
                        return
                    if monotonic() - checked < 1 and not progress["done"]:
                        continue
                    checked = monotonic()
                    if await observer.reads.execution_busy():
                        yield (
                            "data: "
                            + json.dumps(
                                {"error": "Download interrupted: engineering work takes priority."}
                            )
                            + "\n\n"
                        )
                        return
                    yield "data: " + json.dumps(progress) + "\n\n"
        except Exception:  # noqa: BLE001 -- do not expose upstream details
            yield (
                "data: "
                + json.dumps(
                    {
                        "error": "Download failed or timed out. Check private Ollama connectivity and free disk, then retry explicitly."
                    }
                )
                + "\n\n"
            )
        finally:
            observer_runtime.installing = False
            observer.installing = False
            if task:
                observer_runtime.active.discard(task)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def scope_query(task_id: UUID | None = None, team_id: UUID | None = None) -> Scope:
    if task_id and team_id:
        raise HTTPException(422, "Select one scope")
    return Scope(
        "TASK" if task_id else "TEAM" if team_id else "DASHBOARD",
        str(task_id) if task_id else None,
        str(team_id) if team_id else None,
    )


@router.get("/status")
async def status(
    scope: Scope = Depends(scope_query), observer: Observer = Depends(enabled_observer)
) -> dict[str, Any]:
    try:
        return await observer.status(scope)
    except LookupError as exc:
        raise HTTPException(404, "Scope not found") from exc
    except Exception as exc:
        raise HTTPException(
            503, "Observer temporarily unavailable; execution is independent"
        ) from exc


@router.get("/briefing")
async def briefing(
    scope: Scope = Depends(scope_query),
    principal: str = Depends(owner),
    observer: Observer = Depends(enabled_observer),
) -> dict[str, Any]:
    try:
        return await observer.briefing(scope, principal)
    except LookupError as exc:
        raise HTTPException(404, "Scope not found") from exc
    except Exception as exc:
        raise HTTPException(503, "Observer briefing unavailable") from exc


@router.get("/events")
async def events(
    status: Literal["ACTIVE", "ALL", "OPEN", "RESOLVED", "ACKNOWLEDGED", "SNOOZED"] = "ACTIVE",
    scope: Scope = Depends(scope_query),
    observer: Observer = Depends(enabled_observer),
) -> list[dict[str, Any]]:
    return await observer.store.events(scope, status)


@router.post("/events/{identifier}/acknowledge")
async def acknowledge(
    identifier: UUID, observer: Observer = Depends(enabled_observer)
) -> dict[str, bool]:
    if not await observer.store.event_action(str(identifier), "acknowledge", 0):
        raise HTTPException(404, "Active attention event not found")
    return {"acknowledged": True}


@router.post("/events/{identifier}/snooze")
async def snooze(
    identifier: UUID, body: SnoozeInput, observer: Observer = Depends(enabled_observer)
) -> dict[str, bool]:
    if not await observer.store.event_action(str(identifier), "snooze", body.minutes):
        raise HTTPException(404, "Active attention event not found")
    return {"snoozed": True}


@router.put("/preferences")
async def preferences(
    body: PreferenceInput,
    principal: str = Depends(owner),
    observer: Observer = Depends(enabled_observer),
) -> dict[str, Any]:
    return await observer.store.preference(
        principal, body.model_dump(mode="json", exclude_none=True)
    )


@router.post("/questions", status_code=201)
async def question(
    body: QuestionInput,
    principal: str = Depends(owner),
    observer: Observer = Depends(enabled_observer),
) -> dict[str, str]:
    try:
        await observer.reads.snapshot(body.context.scope())
        if not observer_runtime.enabled:
            raise HTTPException(404, "Observer is disabled")
        return await observer.store.create_question(
            principal,
            body.context.scope(),
            body.message,
            str(body.conversation_id) if body.conversation_id else None,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.get("/questions/{identifier}/events")
async def question_events(
    identifier: UUID,
    request: Request,
    principal: str = Depends(owner),
    observer: Observer = Depends(enabled_observer),
) -> StreamingResponse:
    if await observer.store.question(principal, str(identifier)) is None:
        raise HTTPException(404, "Question not found")

    async def stream() -> AsyncIterator[str]:
        task = asyncio.current_task()
        if task:
            observer_runtime.active.add(task)
        try:
            async for event in observer.answer(principal, str(identifier)):
                if await request.is_disconnected():
                    return
                yield "data: " + json.dumps(event) + "\n\n"
        finally:
            if task:
                observer_runtime.active.discard(task)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
async def conversations(
    principal: str = Depends(owner), observer: Observer = Depends(enabled_observer)
) -> list[dict[str, Any]]:
    return await observer.store.conversations(principal)


@router.get("/conversations/{identifier}")
async def conversation(
    identifier: UUID,
    principal: str = Depends(owner),
    observer: Observer = Depends(enabled_observer),
) -> list[dict[str, Any]]:
    try:
        return await observer.store.history(principal, str(identifier))
    except LookupError as exc:
        raise HTTPException(404, "Conversation not found") from exc


@router.get("/usage")
async def usage(observer: Observer = Depends(enabled_observer)) -> dict[str, Any]:
    return await observer.store.usage()
