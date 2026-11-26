"""Environment-driven configuration."""

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()
from pydantic import BaseModel

_INSECURE_SECRETS = {"", "replace-this-secret", "changeme", "secret"}
_MIN_SECRET_LENGTH = 32


class Settings(BaseModel):
    """Runtime settings, read once from the environment."""

    project_id: str
    service_account_json: str | None
    service_account_file: str | None
    jwt_secret: str
    jwt_expires_minutes: int
    cors_origins: list[str]
    clinic_timezone: str
    login_max_attempts: int
    login_window_seconds: int


def _require_jwt_secret() -> str:
    """Refuse to start with a missing or guessable signing key."""
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret in _INSECURE_SECRETS or len(secret) < _MIN_SECRET_LENGTH:
        raise RuntimeError(
            "JWT_SECRET is missing or too weak (need at least 32 characters). "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return secret


@lru_cache
def get_settings() -> Settings:
    origins = [
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if item.strip()
    ]
    return Settings(
        project_id=os.getenv("FIREBASE_PROJECT_ID", ""),
        service_account_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"),
        service_account_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        jwt_secret=_require_jwt_secret(),
        jwt_expires_minutes=int(os.getenv("JWT_EXPIRES_MINUTES", "720")),
        cors_origins=origins,
        clinic_timezone=os.getenv("CLINIC_TIMEZONE", "Asia/Manila"),
        login_max_attempts=int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")),
        login_window_seconds=int(os.getenv("LOGIN_WINDOW_SECONDS", "900")),
    )
