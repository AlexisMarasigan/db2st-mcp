"""Unit tests for `UpstashCache` — uses an in-process fake async Redis."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from db2st_mcp.shared.errors import Db2stError
from db2st_mcp.shared.upstash_cache import CacheCodec


class FakeAsyncRedis:
    """Captures get/set + the EX TTL argument so the test can assert
    that the cache actually sets server-side expiry."""

    def __init__(self, *_: object, **__: object) -> None:
        self._kv: dict[str, Any] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> Any:
        return self._kv.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self._kv[key] = value
        self.set_calls.append((key, value, ex))


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> type[FakeAsyncRedis]:
    fake_module = types.ModuleType("upstash_redis")
    asyncio_module = types.ModuleType("upstash_redis.asyncio")
    asyncio_module.Redis = FakeAsyncRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "upstash_redis", fake_module)
    monkeypatch.setitem(sys.modules, "upstash_redis.asyncio", asyncio_module)
    return FakeAsyncRedis


def _str_codec() -> CacheCodec[str]:
    return CacheCodec(encode=lambda s: s, decode=lambda s: s)


def _make_cache(
    fake_redis: type[FakeAsyncRedis],
    *,
    ttl_seconds: int = 60,
    key_prefix: str = "p",
) -> Any:
    from db2st_mcp.shared.upstash_cache import UpstashCache

    return UpstashCache[str](
        url="https://example.invalid",
        token="x",
        codec=_str_codec(),
        ttl_seconds=ttl_seconds,
        key_prefix=key_prefix,
    )


@pytest.mark.asyncio
async def test_set_then_get_round_trip(fake_redis: type[FakeAsyncRedis]) -> None:
    cache = _make_cache(fake_redis)
    await cache.set("ref-1", "value-1")
    assert await cache.get("ref-1") == "value-1"


@pytest.mark.asyncio
async def test_get_missing_returns_none(fake_redis: type[FakeAsyncRedis]) -> None:
    cache = _make_cache(fake_redis)
    assert await cache.get("never-written") is None


@pytest.mark.asyncio
async def test_set_passes_ex_ttl_to_redis(fake_redis: type[FakeAsyncRedis]) -> None:
    cache = _make_cache(fake_redis, ttl_seconds=120)
    await cache.set("k", "v")
    # Test directly on the underlying fake so we know the TTL really
    # made it to the Redis call (and not just to our wrapper).
    assert cache._redis.set_calls == [("p:k", "v", 120)]


@pytest.mark.asyncio
async def test_key_prefix_applied(fake_redis: type[FakeAsyncRedis]) -> None:
    cache = _make_cache(fake_redis, key_prefix="db2st:shipment")
    await cache.set("ref", "value")
    assert "db2st:shipment:ref" in cache._redis._kv


@pytest.mark.asyncio
async def test_empty_prefix_means_no_separator(
    fake_redis: type[FakeAsyncRedis],
) -> None:
    cache = _make_cache(fake_redis, key_prefix="")
    await cache.set("ref", "value")
    assert "ref" in cache._redis._kv


@pytest.mark.asyncio
async def test_bytes_payload_decoded_to_str(
    fake_redis: type[FakeAsyncRedis],
) -> None:
    """Some Redis clients return bytes; cache must coerce before decode."""
    cache = _make_cache(fake_redis)
    cache._redis._kv["p:k"] = b"value-as-bytes"
    assert await cache.get("k") == "value-as-bytes"


@pytest.mark.asyncio
async def test_codec_round_trip_for_non_string_type(
    fake_redis: type[FakeAsyncRedis],
) -> None:
    """Mirrors the production usage with `Shipment.model_dump_json`."""
    import json

    from db2st_mcp.shared.upstash_cache import UpstashCache

    cache: Any = UpstashCache[dict[str, int]](
        url="https://example.invalid",
        token="x",
        codec=CacheCodec(encode=json.dumps, decode=json.loads),
        ttl_seconds=60,
        key_prefix="p",
    )
    await cache.set("k", {"count": 7})
    assert await cache.get("k") == {"count": 7}


def test_init_rejects_non_positive_ttl(fake_redis: type[FakeAsyncRedis]) -> None:
    with pytest.raises(Db2stError, match="ttl_seconds"):
        _make_cache(fake_redis, ttl_seconds=0)


def test_from_settings_requires_upstash_credentials(
    fake_redis: type[FakeAsyncRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from db2st_mcp.shared.config import Settings
    from db2st_mcp.shared.upstash_cache import UpstashCache

    # Wipe any ambient env vars the dev box may have set.
    for k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    settings = Settings()
    with pytest.raises(Db2stError, match="UPSTASH_REDIS_REST_URL"):
        UpstashCache.from_settings(
            settings,
            codec=_str_codec(),
            key_prefix="p",
        )


def test_from_settings_with_creds_constructs(
    fake_redis: type[FakeAsyncRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from db2st_mcp.shared.config import Settings
    from db2st_mcp.shared.upstash_cache import UpstashCache

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example.invalid")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "secret")
    monkeypatch.setenv("RESPONSE_CACHE_TTL_SECONDS", "30")
    settings = Settings()
    cache = UpstashCache.from_settings(
        settings,
        codec=_str_codec(),
        key_prefix="p",
    )
    assert cache._ttl == 30
