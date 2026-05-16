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

    # Tracking-domain response cache. `memory` is an in-process `TTLCache`
    # (per-pod, lost on restart). `upstash` is the same Upstash Redis
    # database used by `token_store=upstash`, so a cache entry written by
    # one pod is visible to every other pod, and survives pod churn up to
    # the TTL. Kept independent of `token_store` so operators can opt into
    # only one of the two backends.
    response_cache_backend: Literal["memory", "upstash"] = "memory"
    response_cache_ttl_seconds: int = 60

    # DSV / Schenker upstream. `mydsv.dsv.com` is the post-acquisition home
    # of the public tracking API; `www.dbschenker.com` 302-redirects here.
    # Override in deployments behind a corporate proxy or test fixture.
    schenker_base_url: HttpUrl = Field(default=HttpUrl("https://mydsv.dsv.com"))
    schenker_timeout_ms: int = 10_000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()
