"""One-shot live retest of all 11 sample refs against the fixed code.

Bypasses the MCP wire (which is bound to a pre-fix subprocess) and
calls `TrackingService.get_shipment` directly with the full production
stack: SchenkerClient + circuit breaker + cache + Playwright HTML
fallback. Prints one line per ref: ref -> outcome.

Run:
    DB2ST_HTML_FALLBACK=1 uv run python scripts/retest_refs.py
"""

from __future__ import annotations

import asyncio
import os

from db2st_mcp.domains.tracking.server.html_fallback import PlaywrightHtmlFallback
from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.shared.circuit_breaker import CircuitBreaker
from db2st_mcp.shared.errors import Db2stError

SAMPLE_REFS = [
    "1806203236",
    "1806290829",
    "1806273700",
    "1806272330",
    "1806271886",
    "1806270433",
    "1806268072",
    "1806267579",
    "1806264568",
    "1806258974",
    "1806256390",
]


async def main() -> None:
    client = SchenkerClient()
    fallback = PlaywrightHtmlFallback() if os.getenv("DB2ST_HTML_FALLBACK") else None
    breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
    service = TrackingService(client, breaker=breaker, html_fallback=fallback)
    try:
        for ref in SAMPLE_REFS:
            try:
                s = await service.get_shipment(ref)
                detail = (
                    f"OK source={s.source} sender={s.sender.name!r} "
                    f"receiver={s.receiver.name!r} events={len(s.history)}"
                )
            except Db2stError as e:
                detail = f"{type(e).__name__}: {e}"
            except Exception as e:  # noqa: BLE001
                detail = f"RAW {type(e).__name__}: {e}"
            print(f"{ref} -> {detail}")
    finally:
        await client.aclose()
        await service.aclose()


if __name__ == "__main__":
    asyncio.run(main())
