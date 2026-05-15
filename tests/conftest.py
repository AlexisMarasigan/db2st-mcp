"""Test-wide fixtures."""

from __future__ import annotations

import pytest

from db2st_mcp.domains.auth.server.store import InMemoryTokenStore


@pytest.fixture
def in_memory_store() -> InMemoryTokenStore:
    return InMemoryTokenStore()
