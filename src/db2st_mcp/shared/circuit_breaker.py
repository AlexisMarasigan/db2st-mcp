"""Simple per-upstream circuit breaker.

State machine: closed → open → half-open → closed.
- closed: requests flow.
- open: requests short-circuit (caller should fall back).
- half-open: after cooldown, one trial request is allowed.
"""

from __future__ import annotations

import time
from typing import Literal

State = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> State:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self._cooldown:
            return "half_open"
        return "open"

    @property
    def open(self) -> bool:
        return self.state == "open"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()
