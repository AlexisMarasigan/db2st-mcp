"""Unit tests for the in-memory TTL cache."""

from __future__ import annotations

import asyncio

import pytest

from db2st_mcp.shared.cache import TTLCache


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key() -> None:
    cache: TTLCache[str] = TTLCache(maxsize=10, ttl_seconds=60)
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_set_then_get_returns_value() -> None:
    cache: TTLCache[str] = TTLCache(maxsize=10, ttl_seconds=60)
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_eviction_drops_oldest() -> None:
    cache: TTLCache[str] = TTLCache(maxsize=2, ttl_seconds=60)
    await cache.set("a", "1")
    await cache.set("b", "2")
    await cache.set("c", "3")
    assert await cache.get("a") is None
    assert await cache.get("b") == "2"
    assert await cache.get("c") == "3"


@pytest.mark.asyncio
async def test_expires_after_ttl() -> None:
    cache: TTLCache[str] = TTLCache(maxsize=10, ttl_seconds=0.05)
    await cache.set("k", "v")
    await asyncio.sleep(0.06)
    assert await cache.get("k") is None
