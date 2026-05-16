"""Unit tests for `build_deps` — the env-driven dependency wiring.

Pins three branches that are otherwise reached only via deployment:
- `token_store == "upstash"` resolves to `UpstashTokenStore`.
- `DB2ST_HTML_FALLBACK=1` wires the Playwright fallback.
- `DB2ST_HTML_FALLBACK=1` with no playwright install logs a warning
  and leaves the fallback unwired (the service keeps working).
"""

from __future__ import annotations

import sys
import types

import pytest

from db2st_mcp.apps.server.dependencies import build_deps
from db2st_mcp.domains.auth.server.store import InMemoryTokenStore
from db2st_mcp.shared.config import Settings


def test_memory_token_store_is_default() -> None:
    deps = build_deps(Settings(token_store="memory"))
    assert isinstance(deps.token_store, InMemoryTokenStore)
    assert deps.tracking_service is not None


def test_upstash_branch_picks_upstash_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """When `token_store=upstash`, `build_deps` imports and instantiates
    `UpstashTokenStore`. Use a fake `upstash_redis` module so we don't
    need the real network client.
    """

    class _FakeRedis:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

    fake_module = types.ModuleType("upstash_redis")
    asyncio_module = types.ModuleType("upstash_redis.asyncio")
    asyncio_module.Redis = _FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "upstash_redis", fake_module)
    monkeypatch.setitem(sys.modules, "upstash_redis.asyncio", asyncio_module)

    settings = Settings(
        token_store="upstash",
        upstash_redis_rest_url="https://example.invalid",  # type: ignore[arg-type]
        upstash_redis_rest_token="x",
    )
    deps = build_deps(settings)

    from db2st_mcp.domains.auth.server.upstash_store import UpstashTokenStore

    assert isinstance(deps.token_store, UpstashTokenStore)


def test_html_fallback_wired_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB2ST_HTML_FALLBACK", "1")
    deps = build_deps(Settings())
    # The fallback is private on TrackingService; pull it via the
    # known attribute. Service exposes _fallback per its protocol.
    assert deps.tracking_service._fallback is not None


def test_response_cache_defaults_to_memory_ttlcache() -> None:
    """Default `response_cache_backend=memory` wires an in-process
    `TTLCache[Shipment]`."""
    from db2st_mcp.shared.cache import TTLCache

    deps = build_deps(Settings())
    assert isinstance(deps.tracking_service._cache, TTLCache)


def test_response_cache_upstash_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`response_cache_backend=upstash` wires `UpstashCache` end-to-end
    through `build_deps`."""

    class _FakeRedis:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

    fake_module = types.ModuleType("upstash_redis")
    asyncio_module = types.ModuleType("upstash_redis.asyncio")
    asyncio_module.Redis = _FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "upstash_redis", fake_module)
    monkeypatch.setitem(sys.modules, "upstash_redis.asyncio", asyncio_module)

    settings = Settings(
        response_cache_backend="upstash",
        upstash_redis_rest_url="https://example.invalid",  # type: ignore[arg-type]
        upstash_redis_rest_token="x",
    )
    deps = build_deps(settings)

    from db2st_mcp.shared.upstash_cache import UpstashCache

    assert isinstance(deps.tracking_service._cache, UpstashCache)


def test_html_fallback_unavailable_falls_back_to_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `DB2ST_HTML_FALLBACK=1` is set but `playwright` (and our
    module that imports it) is unimportable, `build_deps` logs a
    warning and leaves `_fallback = None`. Simulate the missing
    module by inserting an `ImportError`-raising stand-in.
    """
    monkeypatch.setenv("DB2ST_HTML_FALLBACK", "1")

    import db2st_mcp.domains.tracking.server.html_fallback as hf_module

    # Replace the module entry with one that raises on attribute access.
    class _Boom:
        def __getattr__(self, _name: str) -> object:
            raise ImportError("simulated missing dependency")

    monkeypatch.setitem(sys.modules, hf_module.__name__, _Boom())

    deps = build_deps(Settings())
    assert deps.tracking_service._fallback is None
