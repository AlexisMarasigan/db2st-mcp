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
