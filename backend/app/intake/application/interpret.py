from typing import Protocol

from app.intake.domain.events import Event, Intent, Interpretation, classify


class TextInterpreter(Protocol):
    async def interpret(self, event: Event) -> Interpretation: ...


class InterpretEvent:
    def __init__(
        self, interpreters: tuple[TextInterpreter, ...] = (), *, allow_approval: bool = False
    ) -> None:
        self.interpreters = interpreters
        self.allow_approval = allow_approval

    async def execute(self, event: Event) -> Interpretation:
        deterministic = classify(event)
        if deterministic is not None:
            if (
                deterministic.intent == Intent.APPROVAL
                and event.kind == "comment"
                and not self.allow_approval
            ):
                return Interpretation(Intent.UNKNOWN, 0, "Formal approval required by policy")
            return deterministic
        for interpreter in self.interpreters:
            try:
                result = await interpreter.interpret(event)
            except (TimeoutError, ValueError, ConnectionError):
                continue
            if (
                self.allow_approval
                and event.provider == "github"
                and event.kind == "comment"
                and bool(event.head_sha)
                and result.intent == Intent.APPROVAL
                and result.confidence >= 0.95
            ):
                return Interpretation(Intent.APPROVAL, result.confidence, result.reason, True)
            if result.confidence >= 0.85 and result.intent in {
                Intent.REQUIREMENT_CHANGE,
                Intent.FEEDBACK,
                Intent.IGNORE,
            }:
                return result
        return Interpretation(
            Intent.UNKNOWN, 0, "Human classification required; no reliable interpreter result"
        )
