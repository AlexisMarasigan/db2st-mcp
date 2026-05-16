"""E2E: stdio MCP server's stdout is JSON-RPC only.

If `configure_logging` ever points back at stdout, the stdio MCP
transport's framing breaks (the client sees log lines interleaved with
JSON-RPC frames and rejects them). This test runs the server at
`LOG_LEVEL=info` — the production default — and asserts every stdout
line parses as JSON-RPC.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.e2e


async def _drain_stdout(
    proc: asyncio.subprocess.Process, *, deadline: float
) -> list[bytes]:
    assert proc.stdout is not None
    lines: list[bytes] = []
    while True:
        try:
            remaining = max(0.0, deadline - asyncio.get_event_loop().time())
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
        except TimeoutError:
            return lines
        if not line:
            return lines
        lines.append(line)


@pytest.mark.asyncio
async def test_stdio_stdout_is_jsonrpc_only_at_default_log_level() -> None:
    env = os.environ.copy()
    env["TOKEN_STORE"] = "memory"
    env["LOG_LEVEL"] = "info"  # production default — most likely to log on boot
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
    try:
        # Send initialize so the server has produced at least one stdout frame.
        assert proc.stdin is not None
        proc.stdin.write(
            (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {"tools": {}},
                            "clientInfo": {"name": "e2e", "version": "0.0.1"},
                        },
                    }
                )
                + "\n"
            ).encode()
        )
        await proc.stdin.drain()

        # Read for up to 5s; collect every line emitted to stdout.
        deadline = asyncio.get_event_loop().time() + 5.0
        lines = await _drain_stdout(proc, deadline=deadline)
        assert lines, "server produced no stdout"

        for raw in lines:
            text = raw.decode().rstrip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError as e:
                pytest.fail(f"stdout line is not JSON-RPC: {text!r} ({e})")
            assert msg.get("jsonrpc") == "2.0", (
                f"stdout line is not a JSON-RPC frame: {text!r}"
            )
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except TimeoutError:
            proc.kill()
