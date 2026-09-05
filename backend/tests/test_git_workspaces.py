import base64

from app.infrastructure.git.workspaces import git_authorization_header


def test_git_authorization_header_uses_github_installation_basic_auth() -> None:
    header = git_authorization_header("installation-token")

    scheme, encoded = header.removeprefix("Authorization: ").split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(encoded).decode() == "x-access-token:installation-token"
