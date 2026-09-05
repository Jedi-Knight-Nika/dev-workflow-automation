from app.infrastructure.persistence.terminal_sessions import terminal_token_hash
from app.infrastructure.terminal_runtime import scrub_terminal_output


def test_terminal_tokens_are_stored_as_one_way_hashes() -> None:
    assert terminal_token_hash("secret-token") != "secret-token"
    assert terminal_token_hash("secret-token") == terminal_token_hash("secret-token")


def test_terminal_output_scrubs_common_inline_credentials() -> None:
    output = scrub_terminal_output("API_KEY=abc123 password: hunter2 safe output")
    assert "abc123" not in output
    assert "hunter2" not in output
    assert output.endswith("safe output")
