"""Validate what a Supervisor decision may authorize for its trigger."""


def validate_decision(
    action: str, target_paths: list[str], inventory: list[str], *, anomaly: bool
) -> None:
    allowed = (
        {"CONTINUE", "NUDGE", "STOP"}
        if anomaly
        else {"DELEGATE_IMPLEMENTATION", "DELEGATE_REPAIR", "WAIT_HUMAN"}
    )
    if action not in allowed:
        raise ValueError("Supervisor action does not match trigger")
    if not set(target_paths) <= set(inventory):
        raise ValueError("Supervisor selected a path outside the supplied repository inventory")
