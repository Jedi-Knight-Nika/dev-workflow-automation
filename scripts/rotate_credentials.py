"""Compatibility entrypoint for credential rotation."""

from app.services.credential_rotation import main

if __name__ == "__main__":
    raise SystemExit(main())
