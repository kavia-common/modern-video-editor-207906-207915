import os
from dataclasses import dataclass
from typing import List


def _split_csv(value: str) -> List[str]:
    """Split a CSV string into a list, trimming whitespace and dropping empties."""
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    NOTE: Do not hardcode environment-specific configuration in code.
    """

    db_url: str
    allowed_origins: List[str]
    allowed_methods: List[str]
    allowed_headers: List[str]
    cors_max_age: int
    upload_dir: str


# PUBLIC_INTERFACE
def get_settings() -> Settings:
    """Load Settings from environment variables.

    Required env vars:
    - DATABASE_URL: SQLAlchemy URL. Example: postgresql+asyncpg://user:pass@host:port/db
      If not provided, falls back to DB_CONNECTION_STRING for convenience (see notes).

    Optional:
    - ALLOWED_ORIGINS, ALLOWED_METHODS, ALLOWED_HEADERS, CORS_MAX_AGE
    - UPLOAD_DIR (default: ./uploads)

    Returns:
        Settings: parsed immutable settings object.
    """
    # Prefer DATABASE_URL; allow DB_CONNECTION_STRING as a compatibility fallback.
    # PUBLIC_INTERFACE callers may rely on DATABASE_URL being present in production.
    db_url = os.getenv("DATABASE_URL") or os.getenv("DB_CONNECTION_STRING") or ""
    if not db_url:
        # We deliberately raise early so misconfiguration is obvious in CI/runtime.
        raise RuntimeError(
            "Missing DATABASE_URL (or DB_CONNECTION_STRING) env var for PostgreSQL connection."
        )

    allowed_origins = _split_csv(os.getenv("ALLOWED_ORIGINS", "*"))
    allowed_methods = _split_csv(os.getenv("ALLOWED_METHODS", "GET,POST,PUT,DELETE,PATCH,OPTIONS"))
    allowed_headers = _split_csv(os.getenv("ALLOWED_HEADERS", "*"))
    cors_max_age = int(os.getenv("CORS_MAX_AGE", "3600"))
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")

    return Settings(
        db_url=db_url,
        allowed_origins=allowed_origins,
        allowed_methods=allowed_methods,
        allowed_headers=allowed_headers,
        cors_max_age=cors_max_age,
        upload_dir=upload_dir,
    )
