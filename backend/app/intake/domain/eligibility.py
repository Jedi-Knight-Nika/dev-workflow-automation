from collections.abc import Mapping


def linear_eligible(configuration: Mapping[str, object], assignee: str, state: str) -> bool:
    """Explicit source selection; never infer eligibility from prose or roles."""
    expected = configuration.get("assignee_id")
    states = configuration.get("source_state_ids")
    return (
        isinstance(expected, str)
        and bool(expected)
        and assignee == expected
        and isinstance(states, list)
        and bool(states)
        and all(isinstance(value, str) and bool(value) for value in states)
        and state in states
    )
