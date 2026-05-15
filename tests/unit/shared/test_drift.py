"""Drift detector — fingerprints are stable + warns on shape change."""

from __future__ import annotations

from db2st_mcp.shared import drift
from db2st_mcp.shared.drift import check, fingerprint


def test_fingerprint_stable_for_same_shape() -> None:
    a = {"sender": {"name": "x"}, "events": [{"at": "t", "status": "x"}]}
    b = {"sender": {"name": "y"}, "events": [{"at": "t2", "status": "y"}]}
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_changes_on_added_key() -> None:
    a = {"sender": {"name": "x"}}
    b = {"sender": {"name": "x"}, "newKey": "x"}
    assert fingerprint(a) != fingerprint(b)


def test_check_warns_on_drift(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Reset module-level state between tests.
    drift._seen.clear()
    warnings: list[dict[str, object]] = []

    class _Log:
        def info(self, event: str, **kw: object) -> None:
            pass

        def warning(self, event: str, **kw: object) -> None:
            warnings.append({"event": event, **kw})

    monkeypatch.setattr(drift, "_log", _Log())

    check("/x", {"a": 1})
    check("/x", {"a": 1, "b": 2})

    assert any(w["event"] == "schema.drift" for w in warnings)
