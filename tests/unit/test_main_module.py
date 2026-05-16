"""Pin `python -m db2st_mcp` as a supported invocation.

The console-script entry point (`db2st-mcp`) is the primary surface,
but the dotted-module form is the conventional Python alternative.
Both should produce the same help output.
"""

from __future__ import annotations

import subprocess
import sys


def test_python_dash_m_invocation_shows_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "db2st_mcp", "--help"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert "db2st-mcp" in result.stdout
    assert "serve" in result.stdout
    assert "stdio" in result.stdout
