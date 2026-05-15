"""Smoke test for the shared httpx context manager."""

from __future__ import annotations

import pytest

from db2st_mcp.shared.http import upstream_client


@pytest.mark.asyncio
async def test_upstream_client_yields_a_configured_client() -> None:
    async with upstream_client(base_url="https://example.invalid", timeout_ms=500) as client:
        assert "user-agent" in client.headers
        assert str(client.base_url).startswith("https://example.invalid")
