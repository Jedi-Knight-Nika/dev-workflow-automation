from app.infrastructure.security.crypto import CredentialCipher


def test_credentials_are_encrypted_and_recoverable() -> None:
    cipher = CredentialCipher("a sufficiently long test secret")
    encrypted = cipher.encrypt("provider-key")
    assert b"provider-key" not in encrypted
    assert cipher.decrypt(encrypted) == "provider-key"
