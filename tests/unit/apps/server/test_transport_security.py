"""Unit tests for the MCP transport-security host allowlist plumbing."""

from __future__ import annotations

from typing import Any

import pytest

from db2st_mcp.apps.server.mcp_app import _transport_security
from db2st_mcp.shared.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_no_env_var_uses_sdk_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    assert _transport_security() is None


def test_single_host_extends_allowed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.example.com")
    settings = _transport_security()
    assert settings is not None
    assert settings.enable_dns_rebinding_protection is True
    assert "mcp.example.com" in settings.allowed_hosts
    # SDK defaults are preserved.
    assert "localhost:*" in settings.allowed_hosts
    assert "127.0.0.1:*" in settings.allowed_hosts


def test_multiple_hosts_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "a.example.com, b.example.com ,c.example.com")
    settings = _transport_security()
    assert settings is not None
    for host in ("a.example.com", "b.example.com", "c.example.com"):
        assert host in settings.allowed_hosts


def test_whitespace_only_entries_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", " , ,  ,")
    assert _transport_security() is None
