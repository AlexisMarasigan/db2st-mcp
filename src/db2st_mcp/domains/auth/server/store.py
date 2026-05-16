"""TokenStore implementations.

`InMemoryTokenStore`: dev-only, no persistence across process restarts.
`UpstashTokenStore`: HTTP-based Redis for serverless prod (sprint 2).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, date, datetime
from typing import Literal

from ulid import ULID

from db2st_mcp.domains.auth.shared import (
    RemainingQuota,
    TokenPlan,
    TokenRecord,
)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _gen_secret() -> str:
    return secrets.token_urlsafe(32)


class InMemoryTokenStore:
    """Dev-only TokenStore. State lives in the process."""

    def __init__(self) -> None:
        self._by_hash: dict[str, TokenRecord] = {}
        self._counters: dict[tuple[str, date], int] = {}

    async def lookup(self, secret: str) -> TokenRecord | None:
        return self._by_hash.get(_hash(secret))

    async def consume(self, token_id: str, day: date) -> RemainingQuota | Literal["exhausted"]:
        record = next(
            (r for r in self._by_hash.values() if r.id == token_id),
            None,
        )
        if record is None:
            return "exhausted"
        key = (token_id, day)
        used = self._counters.get(key, 0)
        if used >= record.daily_limit:
            return "exhausted"
        self._counters[key] = used + 1
        return RemainingQuota(record.daily_limit - (used + 1))

    async def mint(self, plan: TokenPlan, daily_limit: int) -> tuple[TokenRecord, str]:
        secret = _gen_secret()
        record = TokenRecord(
            id=str(ULID()),
            hash=_hash(secret),
            plan=plan,
            daily_limit=daily_limit,
            created_at=datetime.now(UTC),
        )
        self._by_hash[record.hash] = record
        return record, secret

    async def revoke(self, token_id: str) -> None:
        for h, r in list(self._by_hash.items()):
            if r.id == token_id:
                self._by_hash[h] = r.model_copy(update={"revoked_at": datetime.now(UTC)})

    async def list(self) -> list[TokenRecord]:
        return list(self._by_hash.values())


__all__ = ["InMemoryTokenStore"]
