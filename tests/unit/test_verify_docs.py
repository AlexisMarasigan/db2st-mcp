"""Lock in: `scripts/verify_docs.py` reports no CRITICAL/WARNING for the repo.

Runs the actual script via runpy so it exercises the real CLI entrypoint
and not a refactored library API.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_run() -> object:
    """Import the script as a module and return its `run` callable."""
    spec = importlib.util.spec_from_file_location(
        "_verify_docs", REPO / "scripts" / "verify_docs.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_verify_docs"] = module
    spec.loader.exec_module(module)
    return module.run


def test_verify_docs_passes_on_current_tree() -> None:
    """Repo currently has 0 CRITICAL and 0 WARNING findings."""
    run = _load_run()
    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = run()  # type: ignore[operator]
    text = buf.getvalue()
    assert exit_code == 0, f"verify-docs exited with {exit_code}\n{text}"
    assert "Criticals: 0" in text or "All checks passed" in text
    assert "Warnings:  0" in text or "All checks passed" in text
