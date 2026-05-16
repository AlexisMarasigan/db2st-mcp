"""DB2ST MCP — Database-to-Structured-Tools MCP server."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("db2st-mcp")
except PackageNotFoundError:  # pragma: no cover — only when running from source pre-install
    __version__ = "0+unknown"
