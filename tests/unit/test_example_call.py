"""Lock in: `scripts/example_call.py` round-trips against a real subprocess.

Verifies the demo client we ship matches the actual MCP server contract,
so README and onboarding instructions stay honest.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_run() -> object:
    spec = importlib.util.spec_from_file_location(
        "_example_call", REPO / "scripts" / "example_call.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_example_call"] = module
    spec.loader.exec_module(module)
    return module.run


def test_example_call_prints_initialize_tools_list_and_call() -> None:
    run = _load_run()
    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = asyncio.run(run("1806203236"))  # type: ignore[operator]
    out = buf.getvalue()
    assert exit_code == 0
    assert "initialize" in out
    assert "tools/list" in out
    assert "track_shipment" in out
    assert "tools/call" in out
