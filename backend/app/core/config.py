"""Application settings, loaded from the environment (or a local `.env` file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# repo root: backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration.

    Every field maps 1:1 to an entry in the repository's `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "Autonomous Maintenance Console"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://amc:amc@localhost:5432/amc",
        description="Async SQLAlchemy DSN. Must use the asyncpg driver.",
    )
    # NoDecode: take the raw env string and split it ourselves, instead of
    # letting pydantic-settings try to JSON-decode it into a list.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    api_prefix: str = "/api/v1"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def sync_database_url(self) -> str:
        """Same DSN, but with a synchronous driver (used by Alembic tooling)."""
        return self.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql+psycopg2://"
        )

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() in {"local", "dev", "development", "test"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — safe to use as a FastAPI dependency."""
    return Settings()


settings = get_settings()
