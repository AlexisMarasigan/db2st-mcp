"""Process-wide configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Loaded once at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    port: int = 8080
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # Auth / quotas
    token_store: Literal["memory", "upstash"] = "memory"
    upstash_redis_rest_url: HttpUrl | None = None
    upstash_redis_rest_token: str | None = None

    # Schenker upstream
    schenker_base_url: HttpUrl = Field(default=HttpUrl("https://www.dbschenker.com"))
    schenker_timeout_ms: int = 10_000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()
