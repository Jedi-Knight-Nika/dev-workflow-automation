import pytest

from app.intake.domain.events import Event
from app.intake.infrastructure.cloud_wire import normalized_usage, request_body, response_text
from app.intake.infrastructure.ollama import classification_messages


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_small_fallback_has_output_limit_and_no_tools_or_transcript(provider: str) -> None:
    event = Event("github", "event", "comment", "10", "Fix the test", "task", authenticated=True)
    url, payload = request_body(provider, "configured-cheap-model", classification_messages(event))
    assert url.startswith("https://api.")
    assert payload.get("max_tokens", payload.get("max_output_tokens")) == 512
    assert "tools" not in payload and "previous_response_id" not in payload
    assert len(payload.get("messages", payload.get("input"))) == 2


def test_unapproved_provider_endpoint_is_not_configurable() -> None:
    with pytest.raises(ValueError):
        request_body("https://attacker.invalid", "model", [])


def test_cloud_usage_does_not_invent_missing_cache_counters() -> None:
    assert not normalized_usage("deepseek", {"prompt_tokens": 3, "completion_tokens": 1}).complete
    usage = normalized_usage(
        "deepseek", {"prompt_tokens": 30, "completion_tokens": 4, "prompt_cache_hit_tokens": 20}
    )
    assert usage.complete and usage.input_tokens == 30 and usage.cache_read_input_tokens == 20


def test_classifier_does_not_silently_truncate_large_new_requirements() -> None:
    with pytest.raises(ValueError, match="large"):
        classification_messages(Event("github", "id", "comment", "user", "ა" * 10000))


def test_empty_provider_content_cannot_be_a_successful_classification() -> None:
    assert response_text("deepseek", {"choices": [{"message": {"content": None}}]}) == ""


def test_openai_cache_writes_are_not_discarded() -> None:
    usage = normalized_usage(
        "openai",
        {
            "input_tokens": 100,
            "output_tokens": 10,
            "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 80},
        },
    )
    assert usage.cache_write_input_tokens == 80 and usage.cache_read_input_tokens == 20
