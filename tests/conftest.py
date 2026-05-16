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
