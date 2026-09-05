import pytest

from app.infrastructure.security.credential_rotation import reencrypt_credentials
from app.infrastructure.security.crypto import CredentialCipher


def test_credential_rotation_reencrypts_every_value() -> None:
    old = CredentialCipher("old-secret-value")
    rotated = reencrypt_credentials(
        [old.encrypt("github-token"), old.encrypt("linear-token")],
        "old-secret-value",
        "new-secret-value",
    )
    new = CredentialCipher("new-secret-value")

    assert [new.decrypt(value) for value in rotated] == ["github-token", "linear-token"]


def test_credential_rotation_fails_before_returning_partial_results() -> None:
    old = CredentialCipher("old-secret-value")

    with pytest.raises(ValueError, match="cannot be decrypted"):
        reencrypt_credentials(
            [old.encrypt("valid"), b"not-valid-ciphertext"],
            "old-secret-value",
            "new-secret-value",
        )
