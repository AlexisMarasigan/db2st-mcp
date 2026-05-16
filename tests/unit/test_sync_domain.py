"""Lock in `scripts/sync_domain.py` behaviour."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "_sync_domain", REPO / "scripts" / "sync_domain.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_domain_in_sync_for_current_repo(capsys) -> None:  # type: ignore[no-untyped-def]
    module = _load_module()
    exit_code = module.run(["--all"])  # type: ignore[attr-defined]
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "in sync" in out
    assert "auth" in out
    assert "tracking" in out


def test_sync_domain_flags_new_exported_symbol(tmp_path: Path) -> None:
    """Synthetic drift: a symbol added to __init__.py but not in DOMAIN.md
    should appear under "Add to Public surface" in the proposal.
    """
    module = _load_module()

    # Build a fake domain tree.
    (tmp_path / "domains" / "fake" / "shared").mkdir(parents=True)
    (tmp_path / "domains" / "fake" / "shared" / "__init__.py").write_text(
        '__all__ = ["NewlyAddedSymbol"]\n'
    )
    (tmp_path / "domains" / "fake" / "DOMAIN.md").write_text(
        "# DOMAIN: fake\nNo mention of the new thing.\n"
    )

    original_root = module.DOMAINS_ROOT  # type: ignore[attr-defined]
    try:
        module.DOMAINS_ROOT = tmp_path / "domains"  # type: ignore[attr-defined]
        module.REPO = tmp_path  # type: ignore[attr-defined]
        proposal = module.proposal_for("fake")  # type: ignore[attr-defined]
    finally:
        module.DOMAINS_ROOT = original_root  # type: ignore[attr-defined]

    assert "Add to Public surface" in proposal
    assert "NewlyAddedSymbol" in proposal
