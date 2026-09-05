import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.models import JobRole
from app.infrastructure.workers.executor import ExecutorProposal, ReviewerProposal
from app.providers import AIProvider, ProviderRequest, ProviderResponse


class IntakeProposal(BaseModel):
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
    if role == JobRole.INTAKE:
        model = IntakeProposal
    elif role == JobRole.THINKER:
        model = ThinkerProposal
    elif role == JobRole.EXECUTOR:
        model = ExecutorProposal
    elif role == JobRole.REVIEWER:
        model = ReviewerProposal
    else:
        raise ValueError(f"Unsupported role {role.value}")
    return model.model_validate(data).model_dump(mode="json")


async def run_with_structured_repair(
    provider: AIProvider,
    request: ProviderRequest,
    role: JobRole,
    max_repairs: int = 2,
) -> tuple[dict[str, Any], list[ProviderAttempt]]:
    attempts: list[ProviderAttempt] = []
    prompt = request.prompt
    cacheable_prefix: str | None = None
    last_error: ValidationError | None = None
    for attempt_number in range(max(0, min(max_repairs, 10)) + 1):
        started = time.monotonic()
        response = await provider.run(
            ProviderRequest(
                model=request.model,
                system=request.system,
                prompt=prompt,
                max_output_tokens=request.max_output_tokens,
                temperature=request.temperature,
                reasoning_effort=request.reasoning_effort,
                timeout_seconds=request.timeout_seconds,
                cacheable_prompt_prefix=cacheable_prefix,
            )
        )
        attempts.append(ProviderAttempt(response, round((time.monotonic() - started) * 1000)))
        try:
            return validate_role_output(role, response.text), attempts
        except ValidationError as exc:
            last_error = exc
            if attempt_number >= max_repairs:
                break
            cacheable_prefix = request.prompt
            prompt = (
                "\n\nYour previous response failed schema validation. Return corrected JSON only. "
                + f"Validation errors: {exc.errors(include_url=False)}. "
                + f"Previous response: {response.text[:8000]}"
            )
    raise StructuredOutputError(
        f"{role.value} returned invalid structured output after {len(attempts)} attempts: "
        f"{last_error}",
        attempts,
    )
