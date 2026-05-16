"""SchenkerClient honours `SCHENKER_BASE_URL` from settings.

Regression: the env var was documented but the client hardcoded
`mydsv.dsv.com`, so anyone overriding to a fixture server or corporate
proxy was silently ignored. This test pins the plumbing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from db2st_mcp.shared.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_client_base_url_follows_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHENKER_BASE_URL", "https://fixture.example.invalid")
    # Re-import the client AFTER the env var is set so settings re-evaluate.
    from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient

    client = SchenkerClient()
    assert str(client._client.base_url).startswith("https://fixture.example.invalid")


def test_client_defaults_to_mydsv_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHENKER_BASE_URL", raising=False)
    from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient

    client = SchenkerClient()
    assert "mydsv.dsv.com" in str(client._client.base_url)
