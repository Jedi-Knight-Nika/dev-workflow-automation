import argparse
import os
from collections.abc import Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Integration
from app.services.crypto import CredentialCipher


def reencrypt_credentials(values: Iterable[bytes], old_secret: str, new_secret: str) -> list[bytes]:
    """Decrypt every value before returning any replacement ciphertext."""
    old_cipher = CredentialCipher(old_secret)
    new_cipher = CredentialCipher(new_secret)
    plaintext = [old_cipher.decrypt(value) for value in values]
    return [new_cipher.encrypt(value) for value in plaintext]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate encrypted integration credentials.")
    parser.add_argument("--apply", action="store_true", help="Commit the rotation")
    args = parser.parse_args()
    settings = get_settings()
    new_secret = os.environ.get("NEW_APP_SECRET_KEY", "")
    if len(new_secret) < 16:
        raise SystemExit("NEW_APP_SECRET_KEY must contain at least 16 characters")
    if new_secret == settings.app_secret_key:
        raise SystemExit("NEW_APP_SECRET_KEY must differ from APP_SECRET_KEY")
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        integrations = list(
            session.scalars(
                select(Integration)
                .where(Integration.encrypted_credentials.is_not(None))
                .order_by(Integration.provider_name)
                .with_for_update()
            ).all()
        )
        replacements = reencrypt_credentials(
            (value for item in integrations if (value := item.encrypted_credentials) is not None),
            settings.app_secret_key,
            new_secret,
        )
        if not args.apply:
            session.rollback()
            print(f"Dry run succeeded for {len(replacements)} credential records.")
            return 0
        if os.environ.get("CONFIRM_CREDENTIAL_ROTATION") != "ROTATE":
            raise SystemExit("Set CONFIRM_CREDENTIAL_ROTATION=ROTATE when using --apply")
        for integration, replacement in zip(integrations, replacements, strict=True):
            integration.encrypted_credentials = replacement
        session.commit()
    print(f"Rotated {len(replacements)} credential records. Update APP_SECRET_KEY before restart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
