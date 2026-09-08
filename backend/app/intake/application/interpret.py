from typing import Protocol

from app.intake.domain.events import Event, Intent, Interpretation, classify


class TextInterpreter(Protocol):
    async def interpret(self, event: Event) -> Interpretation: ...


class InterpretEvent:
    def __init__(self, interpreters: tuple[TextInterpreter, ...] = ()) -> None:
        self.interpreters = interpreters

    async def execute(self, event: Event) -> Interpretation:
        deterministic = classify(event)
        if deterministic is not None:
            return deterministic
        for interpreter in self.interpreters:
            try:
                result = await interpreter.interpret(event)
            except (TimeoutError, ValueError, ConnectionError):
                continue
            if result.confidence >= 0.85 and result.intent in {
                Intent.REQUIREMENT_CHANGE,
                Intent.FEEDBACK,
                Intent.IGNORE,
            }:
                return result
        return Interpretation(
            Intent.UNKNOWN, 0, "Human classification required; no reliable interpreter result"
        )
