"""Allow `python -m db2st_mcp` as an alternative to the `db2st-mcp` console script.

Useful when the wheel is installed but the entry-point binary isn't on PATH
(e.g., inside a sandboxed container, or when comparing behaviour across
multiple installed Python versions).
"""

from __future__ import annotations

from db2st_mcp.apps.server.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
