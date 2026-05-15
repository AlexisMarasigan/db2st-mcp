"""E2E: spawn the db2st-mcp stdio server as a subprocess and round-trip JSON-RPC.

Validates the actual deployment path that Claude Code uses to host this MCP
locally. Exercises:
- the `db2st-mcp` console script,
- the FastMCP stdio transport,
- the tool registry,
- per-tool input validation.

No network is hit: `tools/call` is verified only to the point of returning a
structured envelope; with the rate-limited runner IP the JSON path 404s/429s
upstream and we accept any well-formed JSON-RPC response.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest

pytestmark = pytest.mark.e2e


async def _send(proc: asyncio.subprocess.Process, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    await proc.stdin.drain()
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
    return json.loads(line.decode())  # type: ignore[no-any-return]


async def _notify(proc: asyncio.subprocess.Process, method: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method}) + "\n").encode())
    await proc.stdin.drain()


@pytest.fixture
async def mcp_subprocess() -> AsyncIterator[asyncio.subprocess.Process]:
    """Spawn `python -m db2st_mcp.apps.server.cli stdio` and yield it."""
    env = os.environ.copy()
    env["TOKEN_STORE"] = "memory"
    env["LOG_LEVEL"] = "error"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "db2st_mcp.apps.server.cli",
        "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    yield proc

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except TimeoutError:
        proc.kill()


@pytest.mark.asyncio
async def test_initialize_returns_db2st_server_info(
    mcp_subprocess: asyncio.subprocess.Process,
) -> None:
    response = await _send(
        mcp_subprocess,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "e2e", "version": "0.0.1"},
            },
        },
    )
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    server_info = response["result"]["serverInfo"]
    assert server_info["name"] == "db2st-mcp"


@pytest.mark.asyncio
async def test_tools_list_exposes_track_shipment(
    mcp_subprocess: asyncio.subprocess.Process,
) -> None:
    await _send(
        mcp_subprocess,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "e2e", "version": "0.0.1"},
            },
        },
    )
    await _notify(mcp_subprocess, "notifications/initialized")

    response = await _send(
        mcp_subprocess,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    tool_names = [t["name"] for t in response["result"]["tools"]]
    assert "track_shipment" in tool_names


@pytest.mark.asyncio
async def test_tools_call_returns_well_formed_envelope(
    mcp_subprocess: asyncio.subprocess.Process,
) -> None:
    """Exercises the full transport→service→client path.

    Accepts either a successful payload or a structured MCP error
    (`isError: true`). On the rate-limited test runner IP the upstream
    returns 429 and the service surfaces an `upstream_unavailable` error;
    from a fresh IP the same call returns parsed shipment JSON. Either
    way the JSON-RPC envelope must be well-formed.
    """
    await _send(
        mcp_subprocess,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "e2e", "version": "0.0.1"},
            },
        },
    )
    await _notify(mcp_subprocess, "notifications/initialized")

    response = await _send(
        mcp_subprocess,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "track_shipment",
                "arguments": {"reference": "1806203236"},
            },
        },
        timeout=45,
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 2
    result = response["result"]
    assert "content" in result
    # Either successful (isError absent/False) or a structured error envelope.
    assert isinstance(result.get("isError", False), bool)
