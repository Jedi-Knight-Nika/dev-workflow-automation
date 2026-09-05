import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass(frozen=True)
class GitHubAuth:
    token: str
    installation: bool = False


_token_cache: dict[str, tuple[str, datetime]] = {}
INSTALL_STATE_MAX_AGE_SECONDS = 600


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_install_state(secret: str, now: int | None = None) -> str:
    payload = _b64url(
        json.dumps(
            {
                "issued_at": now if now is not None else int(time.time()),
                "nonce": secrets.token_urlsafe(16),
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = _b64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_install_state(secret: str, state: str, now: int | None = None) -> bool:
    try:
        payload, supplied = state.split(".", 1)
        expected = _b64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        data = json.loads(_b64url_decode(payload))
        issued_at = int(data["issued_at"])
        current = now if now is not None else int(time.time())
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False
    return (
        hmac.compare_digest(expected, supplied)
        and -60 <= current - issued_at <= INSTALL_STATE_MAX_AGE_SECONDS
    )


def github_app_install_url(slug: str, state: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
    if not slug or any(character not in allowed for character in slug):
        raise ValueError("GitHub App slug is invalid")
    return f"https://github.com/apps/{slug}/installations/new?{urlencode({'state': state})}"


def create_app_jwt(app_id: str, private_key: str, now: int | None = None) -> str:
    issued = now or int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"iat": issued - 60, "exp": issued + 540, "iss": app_id}, separators=(",", ":")
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("GitHub App private key must be RSA")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


async def resolve_github_auth(credential: str) -> GitHubAuth:
    try:
        configured = json.loads(credential)
    except json.JSONDecodeError:
        return GitHubAuth(credential)
    if not isinstance(configured, dict) or configured.get("auth_type") != "github_app":
        return GitHubAuth(credential)
    app_id = str(configured.get("app_id", ""))
    installation_id = str(configured.get("installation_id", ""))
    private_key = str(configured.get("private_key", ""))
    if not app_id or not installation_id or not private_key:
        raise ValueError("GitHub App credentials require app_id, installation_id, and private_key")
    cache_key = hashlib.sha256(f"{app_id}:{installation_id}:{private_key}".encode()).hexdigest()
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > datetime.now(UTC) + timedelta(minutes=5):
        return GitHubAuth(cached[0], installation=True)
    jwt = create_app_jwt(app_id, private_key)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "authorization": f"Bearer {jwt}",
                "accept": "application/vnd.github+json",
                "x-github-api-version": "2022-11-28",
            },
        )
        response.raise_for_status()
        body = response.json()
    token = str(body["token"])
    expires_at = datetime.fromisoformat(str(body["expires_at"]))
    _token_cache[cache_key] = (token, expires_at)
    return GitHubAuth(token, installation=True)
