"""Upstash-Redis-backed `TokenStore`.

Optional dependency: install with `pip install db2st-mcp[redis]` or
`uv sync --extra redis`. The import is local to keep the dev image lean.

Schema:
  Hash:  `token:hash:<sha256>` → {id, plan, daily_limit, created_at, revoked_at}
  Index: `token:id:<id>`       → <sha256>   (so revoke by id can find the hash)
  Quota: `quota:<id>:<YYYY-MM-DD>` → counter (TTL 36h)
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, date, datetime
from typing import Any, Literal

from ulid import ULID

from db2st_mcp.domains.auth.shared import RemainingQuota, TokenPlan, TokenRecord
from db2st_mcp.shared.config import Settings
from db2st_mcp.shared.errors import Db2stError


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _gen_secret() -> str:
    return secrets.token_urlsafe(32)


class UpstashTokenStore:
    """TokenStore backed by Upstash Redis (HTTP REST)."""

    def __init__(self, url: str, token: str) -> None:
        try:
            from upstash_redis.asyncio import Redis
        except ImportError as e:  # pragma: no cover — verified at install time
            raise Db2stError("upstash-redis not installed; reinstall with the [redis] extra") from e
        self._redis = Redis(url=url, token=token)

    @classmethod
    def from_settings(cls, settings: Settings) -> UpstashTokenStore:
        if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
            raise Db2stError("UPSTASH_REDIS_REST_URL and _TOKEN must be set")
        return cls(
            url=str(settings.upstash_redis_rest_url),
            token=settings.upstash_redis_rest_token,
        )

    async def lookup(self, secret: str) -> TokenRecord | None:
        raw: Any = await self._redis.get(f"token:hash:{_hash(secret)}")
        if not raw:
            return None
        return _decode_record(raw)

    async def consume(self, token_id: str, day: date) -> RemainingQuota | Literal["exhausted"]:
        key = f"quota:{token_id}:{day.isoformat()}"
        new_count = await self._redis.incr(key)
        # 36h TTL on first write — safe even if INCR raced with another writer.
        if new_count == 1:
            await self._redis.expire(key, 36 * 60 * 60)

        index = await self._redis.get(f"token:id:{token_id}")
        if not index:
            return "exhausted"
        record = _decode_record(await self._redis.get(f"token:hash:{index}"))
        if record is None:
            return "exhausted"

        remaining = record.daily_limit - int(new_count)
        if remaining < 0:
            return "exhausted"
        return RemainingQuota(remaining)

    async def mint(self, plan: TokenPlan, daily_limit: int) -> tuple[TokenRecord, str]:
        secret = _gen_secret()
        record = TokenRecord(
            id=str(ULID()),
            hash=_hash(secret),
            plan=plan,
            daily_limit=daily_limit,
            created_at=datetime.now(UTC),
        )
        encoded = _encode_record(record)
        await self._redis.set(f"token:hash:{record.hash}", encoded)
        await self._redis.set(f"token:id:{record.id}", record.hash)
        return record, secret

    async def revoke(self, token_id: str) -> None:
        index = await self._redis.get(f"token:id:{token_id}")
        if not index:
            return
        record = _decode_record(await self._redis.get(f"token:hash:{index}"))
        if record is None:
            return
        revoked = record.model_copy(update={"revoked_at": datetime.now(UTC)})
        await self._redis.set(f"token:hash:{record.hash}", _encode_record(revoked))

    async def list(self) -> list[TokenRecord]:
        # Upstash supports SCAN. For large tenants iterate; here we keep it simple.
        records: list[TokenRecord] = []
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match="token:hash:*", count=200)
            for key in keys:
                raw = await self._redis.get(key)
                rec = _decode_record(raw)
                if rec is not None:
                    records.append(rec)
            if cursor == 0:
                break
        return records

    async def aclose(self) -> None:
        """Close the underlying httpx connection pool.

        Sibling of `UpstashCache.aclose`; both wrap the same upstash-redis
        client. On graceful shutdown we want the httpx connections
        released cleanly rather than waiting for GC.
        """
        close = getattr(self._redis, "close", None)
        if close is not None:
            await close()


def _encode_record(record: TokenRecord) -> str:
    return record.model_dump_json()


def _decode_record(raw: Any) -> TokenRecord | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return TokenRecord.model_validate_json(raw)
    if isinstance(raw, dict):
        return TokenRecord.model_validate(raw)
    return TokenRecord.model_validate(json.loads(str(raw)))
