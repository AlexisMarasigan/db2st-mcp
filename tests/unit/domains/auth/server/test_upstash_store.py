"""Unit tests for `UpstashTokenStore` — uses a fake async Redis client."""

from __future__ import annotations

import sys
import types
from datetime import UTC, date, datetime
from typing import Any

import pytest

from db2st_mcp.domains.auth.shared import TokenRecord
from db2st_mcp.shared.errors import Db2stError


class FakeAsyncRedis:
    """In-process stand-in for upstash_redis.asyncio.Redis."""

    def __init__(self, *_: object, **__: object) -> None:
        self._kv: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self._kv.get(key)

    async def set(self, key: str, value: Any) -> None:
        self._kv[key] = value

    async def incr(self, key: str) -> int:
        cur = int(self._kv.get(key, 0)) + 1
        self._kv[key] = cur
        return cur

    async def expire(self, _key: str, _ttl: int) -> None:
        return None

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        # Single-shot: return all matching keys then signal done.
        prefix = match.replace("*", "")
        keys = [k for k in self._kv if k.startswith(prefix)]
        return 0, keys


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> type[FakeAsyncRedis]:
    fake_module = types.ModuleType("upstash_redis")
    asyncio_module = types.ModuleType("upstash_redis.asyncio")
    asyncio_module.Redis = FakeAsyncRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "upstash_redis", fake_module)
    monkeypatch.setitem(sys.modules, "upstash_redis.asyncio", asyncio_module)
    return FakeAsyncRedis


def _store(fake_redis: type[FakeAsyncRedis]) -> Any:
    from db2st_mcp.domains.auth.server.upstash_store import UpstashTokenStore

    return UpstashTokenStore(url="https://example.invalid", token="x")


@pytest.mark.asyncio
async def test_mint_then_lookup_round_trip(fake_redis: type[FakeAsyncRedis]) -> None:
    store = _store(fake_redis)
    record, secret = await store.mint(plan="pro", daily_limit=5)
    found = await store.lookup(secret)
    assert isinstance(found, TokenRecord)
    assert found.id == record.id
    assert found.plan == "pro"


@pytest.mark.asyncio
async def test_lookup_unknown_secret_returns_none(
    fake_redis: type[FakeAsyncRedis],
) -> None:
    store = _store(fake_redis)
    assert await store.lookup("nope") is None


@pytest.mark.asyncio
async def test_consume_decrements_and_then_exhausts(
    fake_redis: type[FakeAsyncRedis],
) -> None:
    store = _store(fake_redis)
    record, _ = await store.mint(plan="free", daily_limit=2)
    today = date.today()
    a = await store.consume(record.id, today)
    b = await store.consume(record.id, today)
    c = await store.consume(record.id, today)
    assert a == 1
    assert b == 0
    assert c == "exhausted"


@pytest.mark.asyncio
async def test_revoke_marks_revoked_at(fake_redis: type[FakeAsyncRedis]) -> None:
    store = _store(fake_redis)
    record, secret = await store.mint(plan="free", daily_limit=10)
    await store.revoke(record.id)
    refreshed = await store.lookup(secret)
    assert refreshed is not None
    assert refreshed.revoked_at is not None
    assert isinstance(refreshed.revoked_at, datetime)
    assert refreshed.revoked_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_list_returns_all_records(fake_redis: type[FakeAsyncRedis]) -> None:
    store = _store(fake_redis)
    await store.mint(plan="free", daily_limit=1)
    await store.mint(plan="pro", daily_limit=10)
    records = await store.list()
    assert len(records) == 2


@pytest.mark.asyncio
async def test_from_settings_requires_url_and_token(
    fake_redis: type[FakeAsyncRedis], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    from db2st_mcp.domains.auth.server.upstash_store import UpstashTokenStore
    from db2st_mcp.shared.config import Settings, get_settings

    get_settings.cache_clear()
    with pytest.raises(Db2stError):
        UpstashTokenStore.from_settings(Settings())
