"""Test-wide fixtures + the `--report` CLI option.

The `--report` flag has to be registered in this root conftest (not the
nested `tests/e2e/conftest.py`) so it is recognised regardless of which
test path is passed on the command line. `pytest tests/unit --report`
previously failed with "unrecognized arguments: --report" because pytest
only loads nested conftests after argument parsing. The report-writing
hook still lives in `tests/e2e/conftest.py`; this file owns
registration only.
"""

from __future__ import annotations

import pytest

from db2st_mcp.domains.auth.server.store import InMemoryTokenStore


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--report",
        action="store_true",
        default=False,
        help="Write the Markdown E2E report to docs/E2E-REPORT.md.",
    )


@pytest.fixture
def in_memory_store() -> InMemoryTokenStore:
    return InMemoryTokenStore()


class SpyLogger:
    """Captures structlog `info` / `warning` calls for assertions.

    Used by tests that verify the observability surface emits the
    expected events. Each production module that wants to be spied
    on has a `spy_log` fixture in its own test file that
    monkeypatches that module's `_log` with an instance of this
    class — see `tests/unit/shared/test_circuit_breaker.py` and
    `tests/unit/domains/auth/server/test_middleware.py`.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kw: object) -> None:
        self.calls.append((event, kw))

    def warning(self, event: str, **kw: object) -> None:
        self.calls.append((event, kw))
