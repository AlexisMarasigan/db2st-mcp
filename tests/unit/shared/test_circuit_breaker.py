"""Unit tests for the circuit breaker."""

from __future__ import annotations

import time

from db2st_mcp.shared.circuit_breaker import CircuitBreaker


def test_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
    assert cb.state == "closed"
    assert cb.open is False


def test_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    assert cb.open is True


def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    assert cb.state == "closed"


def test_half_open_after_cooldown() -> None:
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.02)
    cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.03)
    assert cb.state == "half_open"


def test_record_success_closes_after_recovery() -> None:
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.02)
    cb.record_failure()
    cb.record_success()
    assert cb.state == "closed"
