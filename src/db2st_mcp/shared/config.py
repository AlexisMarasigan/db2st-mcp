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

    # MCP transport — allowed Host header values. The SDK defaults to
    # `127.0.0.1:*`, `localhost:*`, `[::1]:*` for DNS-rebinding protection;
    # production deployers behind their own hostname need to extend this.
    # Comma-separated string, e.g. "mcp.example.com,mcp.staging.example.com".
    mcp_allowed_hosts: str = ""

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
