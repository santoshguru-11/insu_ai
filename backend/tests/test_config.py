"""Settings parsing."""

from __future__ import annotations

from app.core.config import Settings


def test_cors_origins_accepts_a_comma_separated_string() -> None:
    settings = Settings(cors_origins="http://localhost:5173, http://127.0.0.1:5173")

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_origins_accepts_a_list() -> None:
    settings = Settings(cors_origins=["http://localhost:5173"])

    assert settings.cors_origins == ["http://localhost:5173"]


def test_log_level_is_normalised() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"


def test_sync_database_url_drops_the_async_driver() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/db")

    assert "asyncpg" not in settings.sync_database_url
