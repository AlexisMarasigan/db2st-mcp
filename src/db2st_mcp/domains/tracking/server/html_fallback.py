"""Playwright-based fallback when the JSON API is unreachable or schema-drifts.

Optional dep — install with `uv sync --extra fallback` (playwright wheel +
the chromium binary). Wired by the service if `DB2ST_HTML_FALLBACK=1`.

Cost: ~1.5–3s per call. Only engaged when the JSON path fails.
"""

from __future__ import annotations

from typing import Any

import structlog

from db2st_mcp.domains.tracking.shared.schemas import (
    Address,
    Party,
    Shipment,
    ShipmentType,
    TrackingEvent,
)
from db2st_mcp.shared.errors import NotFoundError, UpstreamUnavailableError

# Strings the SPA renders when the upstream resolver returns no record.
# Detected here so the tool emits a proper NotFoundError rather than a
# misleading "scraped" event.
NOT_FOUND_MARKERS = (
    "Shipment not found",
    "No shipments were found",
    "could not be found",
)

_log = structlog.get_logger(__name__)


class PlaywrightHtmlFallback:
    """Render the public SPA, then scrape the DOM into a `Shipment`.

    Conservative: surfaces whatever the human reader can see; missing data
    becomes None/empty rather than failing the call.
    """

    SPA_URL = "https://mydsv.dsv.com/app/tracking-public/"

    async def fetch(self, reference: str) -> Shipment:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise UpstreamUnavailableError(
                "playwright not installed (install with the [fallback] extra)"
            ) from e

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/130.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                )
                page = await ctx.new_page()
                await page.goto(f"{self.SPA_URL}?refNumber={reference}", wait_until="networkidle")
                data = await page.evaluate(_EXTRACTION_SCRIPT)
            finally:
                await browser.close()

        if not data:
            _log.warning("html_fallback.empty", reference=reference)
            return Shipment(reference=reference, source="html_fallback")

        body = str(data.get("bodyText") or "")
        if any(marker in body for marker in NOT_FOUND_MARKERS):
            raise NotFoundError(
                "shipment not found (html fallback)", details={"reference": reference}
            )

        return _to_shipment(reference, data)


_EXTRACTION_SCRIPT = """
() => {
  const text = (sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  };
  const all = (sel) => Array.from(document.querySelectorAll(sel)).map(e => e.textContent.trim());
  return {
    bodyText: document.body.innerText || "",
    senderName: text('[data-testid="sender-name"], .sender-name'),
    receiverName: text('[data-testid="receiver-name"], .receiver-name'),
    events: all('[data-testid="tracking-event"], .tracking-event'),
  };
}
"""


def _to_shipment(reference: str, data: dict[str, Any]) -> Shipment:
    """Map the scraped data to a `Shipment`. Conservative — best-effort fields."""
    type_hint: ShipmentType = "unknown"
    sender = Party(name=str(data.get("senderName") or ""), address=Address())
    receiver = Party(name=str(data.get("receiverName") or ""), address=Address())

    history: list[TrackingEvent] = []
    # The scraped events are text-only; tests can extend this when the SPA
    # exposes data attributes. Surface the body text as a single "scraped"
    # event so downstream consumers see *something*.
    body = data.get("bodyText")
    if body:
        try:
            from datetime import UTC, datetime

            history.append(
                TrackingEvent(
                    at=datetime.now(UTC),
                    location=None,
                    status="scraped",
                    description=str(body)[:400],
                )
            )
        except Exception:  # pragma: no cover  # nosec B110  — intentional swallow
            # Cosmetic enrichment (a stamped "scraped" event with the
            # body text). Never let it break the fallback path.
            pass

    return Shipment(
        reference=reference,
        type=type_hint,
        sender=sender,
        receiver=receiver,
        history=history,
        source="html_fallback",
    )
