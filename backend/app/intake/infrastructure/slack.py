import hashlib
import hmac


def verify_slack_signature(
    *, body: bytes, timestamp: str, signature: str, secret: str, now: int
) -> bool:
    """Authenticate the raw body before parsing it. Replay dedup is a DB concern."""
    if not secret or len(body) > 1_000_000:
        return False
    try:
        issued = int(timestamp)
    except ValueError:
        return False
    if abs(now - issued) > 300:
        return False
    digest = hmac.new(
        secret.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest("v0=" + digest, signature)
