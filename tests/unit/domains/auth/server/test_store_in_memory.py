"""Unit tests for `InMemoryTokenStore`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from db2st_mcp.domains.auth.server.store import InMemoryTokenStore


@pytest.mark.asyncio
async def test_mint_then_lookup_returns_record() -> None:
    store = InMemoryTokenStore()
    record, secret = await store.mint(plan="free", daily_limit=10)

    found = await store.lookup(secret)
    assert found is not None
    assert found.id == record.id
    assert found.plan == "free"
    assert found.daily_limit == 10


@pytest.mark.asyncio
async def test_lookup_unknown_secret_returns_none() -> None:
    store = InMemoryTokenStore()
    assert await store.lookup("nope") is None


@pytest.mark.asyncio
async def test_consume_decrements_and_eventually_exhausts() -> None:
    store = InMemoryTokenStore()
    record, _ = await store.mint(plan="free", daily_limit=3)
    today = datetime.now(UTC).date()

    first = await store.consume(record.id, today)
    second = await store.consume(record.id, today)
    third = await store.consume(record.id, today)
    fourth = await store.consume(record.id, today)

    assert first == 2
    assert second == 1
    assert third == 0
    assert fourth == "exhausted"


@pytest.mark.asyncio
async def test_revoke_marks_revoked_at() -> None:
    store = InMemoryTokenStore()
    record, _ = await store.mint(plan="pro", daily_limit=100)

    await store.revoke(record.id)
    all_records = await store.list()

    assert all_records[0].revoked_at is not None
