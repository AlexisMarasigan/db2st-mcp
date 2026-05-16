"""Upstash-Redis-backed cache. Optional, generic on the cached value type.

Symmetric to `UpstashTokenStore`: same HTTP REST backend, same import-time
optional dependency. The cache is generic on `T`; callers inject an encode
/ decode pair so the cache stays domain-agnostic.

Keys are prefixed (e.g. `db2st:shipment:<ref>`) to avoid collisions when
multiple workloads share a single Upstash database.

TTL is enforced by Redis itself (SET ... EX <seconds>), so an expired
entry is simply gone on the next GET — no client-side eviction needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from db2st_mcp.shared.config import Settings
from db2st_mcp.shared.errors import Db2stError

T = TypeVar("T")


@dataclass(frozen=True)
class CacheCodec(Generic[T]):
    """Encode / decode pair so `UpstashCache` stays generic.

    Inject from the domain that owns the cached type. Keeps `shared/`
    free of domain imports.
    """

    encode: Callable[[T], str]
    decode: Callable[[str], T]


class UpstashCache(Generic[T]):
    """Cache backed by Upstash Redis (HTTP REST). Matches the duck-typed
    `_Cache` Protocol used by `TrackingService` (async get / set on str
    keys)."""

    def __init__(
        self,
        *,
        url: str,
        token: str,
        codec: CacheCodec[T],
        ttl_seconds: int,
        key_prefix: str = "",
    ) -> None:
        try:
            from upstash_redis.asyncio import Redis
        except ImportError as e:  # pragma: no cover — verified at install time
            raise Db2stError("upstash-redis not installed; reinstall with the [redis] extra") from e
        if ttl_seconds <= 0:
            raise Db2stError("UpstashCache requires ttl_seconds > 0")
        self._redis = Redis(url=url, token=token)
        self._codec = codec
        self._ttl = ttl_seconds
        self._prefix = key_prefix.rstrip(":")

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        codec: CacheCodec[T],
        key_prefix: str,
        ttl_seconds: int | None = None,
    ) -> UpstashCache[T]:
        if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
            raise Db2stError(
                "UPSTASH_REDIS_REST_URL and _TOKEN must be set when response_cache_backend=upstash"
            )
        return cls(
            url=str(settings.upstash_redis_rest_url),
            token=settings.upstash_redis_rest_token,
            codec=codec,
            ttl_seconds=ttl_seconds or settings.response_cache_ttl_seconds,
            key_prefix=key_prefix,
        )

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}" if self._prefix else key

    async def get(self, key: str) -> T | None:
        raw: Any = await self._redis.get(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return self._codec.decode(str(raw))

    async def set(self, key: str, value: T) -> None:
        encoded = self._codec.encode(value)
        # SET with EX argument — Redis handles expiry server-side, so the
        # cache survives pod restarts up to the TTL. upstash-redis maps
        # the `ex=` kwarg to the SET ... EX <seconds> form.
        await self._redis.set(self._key(key), encoded, ex=self._ttl)

    async def aclose(self) -> None:
        """Close the underlying httpx connection pool.

        upstash-redis wraps httpx; without an explicit close, the pool
        stays open until GC. On graceful shutdown (SIGTERM) we want the
        connections released cleanly.
        """
        close = getattr(self._redis, "close", None)
        if close is not None:
            await close()
