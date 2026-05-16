"""CLI tests — argparse routing + mint/list/revoke against in-memory store."""

from __future__ import annotations

import json
from typing import Any

import pytest

from db2st_mcp.apps.server import cli


@pytest.fixture
def memory_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_STORE", "memory")
    monkeypatch.setenv("PORT", "8080")
    # Reset cached settings so monkeypatched env wins.
    from db2st_mcp.shared.config import get_settings

    get_settings.cache_clear()


def test_unknown_command_exits_with_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])
    assert exc.value.code == 2


def test_mint_prints_secret_once(memory_settings: None, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["mint", "--plan", "pro", "--limit", "50"])
    assert rc == 0
    out = capsys.readouterr().out
    payload: dict[str, Any] = json.loads(out)
    assert payload["plan"] == "pro"
    assert payload["daily_limit"] == 50
    assert payload["secret"]
    assert payload["id"]


def test_tokens_list_runs(memory_settings: None, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tokens", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []  # nothing minted in fresh store


def test_tokens_revoke_runs(memory_settings: None, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["tokens", "revoke", "01HXX"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "revoked"


def test_tokens_without_subcommand_errors(
    memory_settings: None, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["tokens"])
    assert rc == 2


def test_serve_dispatch_calls_uvicorn(
    memory_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`serve` subcommand routes to `uvicorn.run` with the configured
    app + host + port. Mock uvicorn so the test doesn't actually bind.
    """
    captured: dict[str, Any] = {}

    def fake_run(app: str, **kwargs: Any) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(cli, "uvicorn", type("FakeUv", (), {"run": staticmethod(fake_run)}))

    rc = cli.main(["serve", "--host", "127.0.0.1", "--port", "9999"])
    assert rc == 0
    assert captured["app"] == "db2st_mcp.apps.server.main:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9999


def test_stdio_dispatch_runs_mcp_loop(
    memory_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`stdio` subcommand dispatches to `_cmd_stdio`, which calls
    `mcp.run_stdio_async()` inside `asyncio.run`. Mock the inner
    method so the test doesn't actually attach to stdio.
    """

    async def fake_run_stdio_async(_self: Any) -> None:
        return None

    from mcp.server.fastmcp import FastMCP

    monkeypatch.setattr(FastMCP, "run_stdio_async", fake_run_stdio_async)

    rc = cli.main(["stdio"])
    assert rc == 0
