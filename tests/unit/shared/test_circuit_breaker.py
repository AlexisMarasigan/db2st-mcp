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
    before = cb.state
    assert before == "closed"
    cb.record_failure()
    after = cb.state
    assert after == "open"
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
    before_cooldown = cb.state
    assert before_cooldown == "open"
    time.sleep(0.03)
    after_cooldown = cb.state
    assert after_cooldown == "half_open"


def test_record_success_closes_after_recovery() -> None:
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.02)
    cb.record_failure()
    cb.record_success()
    assert cb.state == "closed"


def test_opens_emits_warning_log() -> None:
    """Ops dashboards need to see breaker-trip events. Pinned because
    a silent breaker is operationally invisible — first symptom would
    be elevated upstream_unavailable response rates with no trigger."""
    import db2st_mcp.shared.circuit_breaker as cb_module

    captured: list[tuple[str, dict[str, object]]] = []

    class _SpyLogger:
        def info(self, event: str, **kw: object) -> None:
            captured.append((event, kw))

        def warning(self, event: str, **kw: object) -> None:
            captured.append((event, kw))

    cb_module._log = _SpyLogger()
    try:
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)
        cb.record_failure()  # below threshold, no log
        assert captured == []
        cb.record_failure()  # hits threshold → opens → warning log
        assert len(captured) == 1
        event, kw = captured[0]
        assert event == "circuit_breaker.opened"
        assert kw["failures"] == 2
        assert kw["threshold"] == 2
        assert kw["cooldown_seconds"] == 10
    finally:
        # Restore the real logger so other tests in the same suite
        # don't keep our spy.
        import structlog

        cb_module._log = structlog.get_logger(cb_module.__name__)


def test_closes_after_open_emits_info_log() -> None:
    """The closed → open trip is a warning. The open → closed
    recovery is operationally useful too — it signals the upstream
    recovered. Logged at info, not warning, since it's good news."""
    import db2st_mcp.shared.circuit_breaker as cb_module

    captured: list[tuple[str, dict[str, object]]] = []

    class _SpyLogger:
        def info(self, event: str, **kw: object) -> None:
            captured.append((event, kw))

        def warning(self, event: str, **kw: object) -> None:
            captured.append((event, kw))

    cb_module._log = _SpyLogger()
    try:
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
        cb.record_failure()  # opens (1 warning event captured)
        cb.record_success()  # closes (1 info event captured)
        events = [e for e, _ in captured]
        assert events == ["circuit_breaker.opened", "circuit_breaker.closed"]

        # A second record_success on an already-closed breaker must
        # NOT log — otherwise every healthy request would emit one.
        captured.clear()
        cb.record_success()
        assert captured == []
    finally:
        import structlog

        cb_module._log = structlog.get_logger(cb_module.__name__)
