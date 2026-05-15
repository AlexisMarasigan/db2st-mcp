"""In-memory TTL cache. Process-local. Survives no restarts.

Sized for the tracking domain's response cache (per-ref shipment). Larger
caches should swap to Redis. Threadsafe-ish — fine for the asyncio single-
threaded model FastAPI uses by default.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Bounded TTL cache with LRU eviction."""

    def __init__(self, *, maxsize: int = 1024, ttl_seconds: float = 60.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()

    async def get(self, key: str) -> T | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() >= expires_at:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    async def set(self, key: str, value: T) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __len__(self) -> int:  # for tests
        return len(self._data)
