import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CredentialCipher:
    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode()
        except InvalidToken as exc:
            raise ValueError(
                "Credential cannot be decrypted with the configured application key"
            ) from exc


cipher = CredentialCipher(get_settings().app_secret_key)
