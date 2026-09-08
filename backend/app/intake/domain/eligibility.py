from collections.abc import Mapping


def linear_eligible(configuration: Mapping[str, object], assignee: str, state: str) -> bool:
    """Explicit V2 source selection; never infer eligibility from prose or roles."""
    expected = configuration.get("v2_assignee_id")
    states = configuration.get("v2_source_state_ids")
    return (
        isinstance(expected, str)
        and bool(expected)
        and assignee == expected
        and isinstance(states, list)
        and bool(states)
        and all(isinstance(value, str) and bool(value) for value in states)
        and state in states
    )
