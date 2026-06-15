"""Runtime configuration loaded from environment and ``.env``.

``Settings`` is the single source of truth for environment-driven config.
``get_settings()`` is cached so all parts of the app see the same instance.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_dotenv() -> Path | None:
    """Walk up from this file looking for a repo-root ``.env``."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
        if (parent / "pyproject.toml").is_file() and (parent / ".git").exists():
            return None
    return None


class Settings(BaseSettings):
    """Typed view of the environment for the agentic-ecommerce monorepo."""

    model_config = SettingsConfigDict(
        env_file=_find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        description=(
            "SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@localhost:5432/agentic_ecommerce"
        ),
    )
    jwt_secret_key: SecretStr = Field(
        description="HMAC secret used to sign JWTs. Required — no default.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)

    rate_limit_enabled: bool = Field(
        default=True,
        description=(
            "Master switch for the slowapi limiter. Disabled in tests so the "
            "suite doesn't accidentally trip per-IP limits."
        ),
    )
    rate_limit_login: str = Field(
        default="5/minute",
        description="slowapi limit expression applied to POST /auth/login.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
