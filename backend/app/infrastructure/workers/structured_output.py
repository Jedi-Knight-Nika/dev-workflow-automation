import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.models import JobRole
from app.infrastructure.workers.executor import ExecutorProposal, ReviewerProposal, TesterProposal
from app.infrastructure.workers.repository_tools import RepositoryTools
from app.providers import AIProvider, ProviderRequest, ProviderResponse
from app.providers.streaming import collect_provider_stream


class ExternalDeliveryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "UPDATE_PR_TITLE",
        "UPDATE_PR_BODY",
        "UPDATE_COMMIT_MESSAGE",
        "MERGE_PULL_REQUEST",
    ]
    value: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "ExternalDeliveryAction":
        if (
            self.action
            in {
                "UPDATE_PR_TITLE",
                "UPDATE_PR_BODY",
                "UPDATE_COMMIT_MESSAGE",
            }
            and not self.value
        ):
            raise ValueError(f"{self.action} requires a value")
        if (
            self.action in {"UPDATE_PR_TITLE", "UPDATE_COMMIT_MESSAGE"}
            and self.value
            and len(self.value) > 256
        ):
            raise ValueError(f"{self.action} exceeds the supported length")
        if self.action == "UPDATE_PR_BODY" and self.value and len(self.value) > 65_536:
            raise ValueError("UPDATE_PR_BODY exceeds the supported body length")
        if self.action == "MERGE_PULL_REQUEST" and self.value is not None:
            raise ValueError("MERGE_PULL_REQUEST does not accept a value")
        return self


class ConsultationReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["CONSULTATION_REPLIED"]
    summary: str = Field(min_length=1, max_length=8000)


class DelivererProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["EVENT_INTERPRETED"]
    event_type: Literal[
        "NEW_TASK",
        "INFORMATIONAL",
        "REVIEW_FIX",
        "ARCHITECTURAL_FINDING",
        "REQUIREMENT_CHANGE",
        "NEEDS_HUMAN",
    ]
    actionability: Literal["ACTION_REQUIRED", "INFORMATIONAL", "NEEDS_HUMAN"]
    blocking: bool
    summary: str
    confidence: float = Field(ge=0, le=1)
    repository_ids: list[str] = Field(default_factory=list)
    repository_selection_reason: str = ""
    external_delivery_actions: list[ExternalDeliveryAction]


class ThinkerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["PLAN_READY", "NEEDS_CONTEXT", "NEEDS_HUMAN"]
    goal: str = ""
    targets: list[str] = Field(default_factory=list)
    ordered_steps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    reason: str = ""
    questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> "ThinkerProposal":
        if self.result == "PLAN_READY":
            if not self.goal or not self.ordered_steps or not self.acceptance_criteria:
                raise ValueError("PLAN_READY requires goal, ordered_steps, and acceptance_criteria")
        elif not self.reason:
            raise ValueError(f"{self.result} requires a reason")
        if self.result == "NEEDS_CONTEXT" and not self.questions:
            raise ValueError("NEEDS_CONTEXT requires at least one question")
        return self


@dataclass(frozen=True)
class ProviderAttempt:
    response: ProviderResponse
    duration_ms: int


class StructuredOutputError(RuntimeError):
    def __init__(self, message: str, attempts: list[ProviderAttempt]) -> None:
        super().__init__(message)
        self.attempts = attempts


class ProviderRunInterrupted(RuntimeError):
    """Retain paid usage without turning a provider outage into a protocol error."""

    def __init__(self, cause: RuntimeError, attempts: list[ProviderAttempt]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.attempts = attempts


def parse_model_data(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1])
        candidate = candidate.removeprefix("json\n")
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return {"text": text}
    return value if isinstance(value, dict) else {"value": value}


def validate_role_output(role: JobRole, text: str) -> dict[str, Any]:
    data = parse_model_data(text)
    model: type[BaseModel]
    if role == JobRole.DELIVERER:
        model = DelivererProposal
    elif role == JobRole.THINKER:
        model = ThinkerProposal
    elif role == JobRole.EXECUTOR:
        model = ExecutorProposal
    elif role == JobRole.REVIEWER:
        model = ReviewerProposal
    elif role == JobRole.TESTER:
        model = TesterProposal
    else:
        raise ValueError(f"Unsupported role {role.value}")
    return model.model_validate(data).model_dump(mode="json")


def role_output_schema(role: JobRole) -> dict[str, Any]:
    models: dict[JobRole, type[BaseModel]] = {
        JobRole.DELIVERER: DelivererProposal,
        JobRole.THINKER: ThinkerProposal,
        JobRole.EXECUTOR: ExecutorProposal,
        JobRole.REVIEWER: ReviewerProposal,
        JobRole.TESTER: TesterProposal,
    }
    try:
        return models[role].model_json_schema()
    except KeyError as exc:
        raise ValueError(f"Unsupported role {role.value}") from exc


async def run_with_structured_repair(
    provider: AIProvider,
    request: ProviderRequest,
    role: JobRole,
    max_repairs: int = 1,
    before_attempt: Callable[[list[ProviderAttempt]], Awaitable[None]] | None = None,
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    is_cancelled: Callable[[], Awaitable[bool]] | None = None,
    repository_tools: RepositoryTools | None = None,
    response_model: type[BaseModel] | None = None,
    max_model_calls: int = 20,
) -> tuple[dict[str, Any], list[ProviderAttempt]]:
    attempts: list[ProviderAttempt] = []
    if repository_tools is not None:
        repository_tools.begin_history()
    prompt = request.prompt
    cacheable_prefix: str | None = request.cacheable_prompt_prefix
    last_error: ValidationError | None = None
    history: tuple[dict[str, Any], ...] = ()
    for attempt_number in range(max(0, min(max_repairs, 10)) + 1):
        if len(attempts) >= max_model_calls:
            raise StructuredOutputError("Model-turn budget exhausted", attempts)
        if before_attempt is not None:
            await before_attempt(attempts)
        started = time.monotonic()
        pending_request = ProviderRequest(
            model=request.model,
            system=request.system,
            prompt=prompt,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            reasoning_effort=request.reasoning_effort,
            timeout_seconds=request.timeout_seconds,
            cacheable_prompt_prefix=cacheable_prefix,
            response_schema=request.response_schema,
            tools=request.tools,
        )
        if repository_tools is not None and provider.supports_repository_tools:
            while True:
                if len(attempts) >= max_model_calls:
                    raise StructuredOutputError("Model-turn budget exhausted", attempts)
                if is_cancelled is not None and await is_cancelled():
                    raise ProviderRunInterrupted(
                        RuntimeError("Worker cancelled during repository inspection"), attempts
                    )
                if history and before_attempt is not None:
                    await before_attempt(attempts)
                started = time.monotonic()
                try:
                    # Reserve the last call for a deliverable, retaining all source evidence.
                    final_turn = (
                        len(attempts) >= max_model_calls - 1
                        or repository_tools.calls >= repository_tools.max_calls
                        or repository_tools.remaining <= 0
                        or repository_tools.repeated_reads >= 2
                        or attempt_number > 0
                    )
                    response = await provider.run(
                        replace(
                            pending_request,
                            tool_history=history,
                            allow_tool_calls=not final_turn,
                            system=pending_request.system
                            + (
                                "\nRepository inspection is complete for this run. Return your "
                                "structured result using the evidence already read. If essential "
                                "evidence is missing, identify the exact unresolved files; do not "
                                "invent source or report unverified success."
                                if final_turn
                                else ""
                            ),
                        )
                    )
                except RuntimeError as exc:
                    raise ProviderRunInterrupted(exc, attempts) from exc
                attempts.append(
                    ProviderAttempt(response, round((time.monotonic() - started) * 1000))
                )
                if not response.tool_calls:
                    if on_text_delta and response.text:
                        await on_text_delta(response.text)
                    break
                history += response.continuation
                for call in response.tool_calls:
                    if is_cancelled is not None and await is_cancelled():
                        raise ProviderRunInterrupted(
                            RuntimeError("Worker cancelled before workspace operation"), attempts
                        )
                    name = str(call.get("name", ""))
                    if on_text_delta:
                        await on_text_delta(f"\nUsing {name}\n")
                    try:
                        output = await repository_tools.execute(
                            name, str(call.get("arguments", "{}"))
                        )
                    except RuntimeError as exc:
                        raise StructuredOutputError(str(exc), attempts) from exc
                    approval_id = getattr(repository_tools, "approval_id", None)
                    if approval_id is not None:
                        return {
                            "result": "NEEDS_HUMAN",
                            "summary": "Workspace operation requires policy approval",
                            "reason": f"Approve workspace operation {approval_id} before resuming.",
                        }, attempts
                    if repository_tools.consultation is not None:
                        return {
                            "result": "CONSULTATION_REQUESTED",
                            **repository_tools.consultation,
                        }, attempts
                    history += (
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": output,
                        },
                    )
        else:
            response = await collect_provider_stream(
                provider, pending_request, on_text_delta, is_cancelled
            )
            attempts.append(ProviderAttempt(response, round((time.monotonic() - started) * 1000)))
        try:
            if response_model is not None:
                return response_model.model_validate(parse_model_data(response.text)).model_dump(
                    mode="json"
                ), attempts
            return validate_role_output(role, response.text), attempts
        except ValidationError as exc:
            last_error = exc
            if attempt_number >= max_repairs:
                break
            cacheable_prefix = request.prompt
            prompt = (
                "\n\nYour previous response failed schema validation. Return corrected JSON only. "
                + f"Validation errors: {exc.errors(include_url=False, include_input=False)}. "
                + f"Previous response: {response.text[:8000]}"
            )
    raise StructuredOutputError(
        f"{role.value} returned invalid structured output after {len(attempts)} attempts: "
        f"{last_error}",
        attempts,
    )
