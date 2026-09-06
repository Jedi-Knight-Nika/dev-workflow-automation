import base64
import json
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.integrations.github import verify_signature
from app.integrations.github_auth import (
    create_app_jwt,
    create_install_state,
    github_app_install_url,
    resolve_github_auth,
    verify_install_state,
)


def test_github_signature_matches_official_vector() -> None:
    assert verify_signature(
        b"Hello, World!",
        "It's a Secret to Everybody",
        "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17",
    )


def test_github_signature_rejects_invalid_value() -> None:
    assert not verify_signature(b"payload", "secret", "sha256=invalid")
    assert not verify_signature(b"payload", "", None)


def github_private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_github_app_jwt_has_bounded_official_claims() -> None:
    token = create_app_jwt("123", github_private_key(), now=1_000)
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))

    assert claims == {"iat": 940, "exp": 1540, "iss": "123"}


def test_github_install_state_is_signed_and_expires() -> None:
    state = create_install_state("secret", now=1_000)

    assert verify_install_state("secret", state, now=1_030)
    assert not verify_install_state("wrong", state, now=1_030)
    assert not verify_install_state("secret", state, now=1_601)
    assert not verify_install_state("secret", f"{state}x", now=1_030)
    assert not verify_install_state("secret", "not-base64.signature", now=1_030)


def test_github_app_install_url_is_scoped_to_slug_and_state() -> None:
    url = github_app_install_url("engineering-worker", "signed.state")

    assert url == (
        "https://github.com/apps/engineering-worker/installations/new?state=signed.state"
    )
    with pytest.raises(ValueError, match="slug is invalid"):
        github_app_install_url("../wrong", "state")


@pytest.mark.asyncio
async def test_github_app_credential_exchanges_for_installation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app/installations/456/access_tokens"
        assert request.headers["authorization"].startswith("Bearer eyJ")
        return httpx.Response(
            201, json={"token": "ghs_installation", "expires_at": "2099-01-01T00:00:00Z"}
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    credential = json.dumps(
        {
            "auth_type": "github_app",
            "app_id": "123",
            "installation_id": "456",
            "private_key": github_private_key(),
        }
    )
    auth = await resolve_github_auth(credential)

    assert auth.token == "ghs_installation"
    assert auth.installation is True


@pytest.mark.asyncio
async def test_plain_github_token_remains_supported() -> None:
    auth = await resolve_github_auth("github_pat_existing")
    assert auth.token == "github_pat_existing"
    assert auth.installation is False
