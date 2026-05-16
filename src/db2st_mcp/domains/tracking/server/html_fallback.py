"""Playwright-based fallback when the JSON API is unreachable or schema-drifts.

Optional dep — install with `uv sync --extra fallback` (playwright wheel +
the chromium binary). Wired by the service if `DB2ST_HTML_FALLBACK=1`.

Cost: ~1.5–3s per call. Only engaged when the JSON path fails.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from db2st_mcp.domains.tracking.shared.schemas import (
    Address,
    PackageInfo,
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

# Strings the SPA renders only when the shipment-detail view has loaded.
# At least one must be present in the scraped body for the fallback to
# be considered successful. If none match (and no not-found marker
# matches either), the SPA is on its landing/search state — typically
# because the resolver XHR was rate-limited or the headless context
# never primed an XSRF cookie. That's an upstream-unavailable
# condition, not an empty shipment.
#
# Markers include both English and Swedish — the SPA mixes locales
# (Swedish chrome + English content fields), so requiring either is
# safe and resists future locale flips.
DETAIL_MARKERS = (
    "DWB Number",
    "DWB-nummer",
    "STT Number",
    "STT-number",
    "STT-nummer",
    "Number of packages",
    "Antal kollin",
    "Show all events",
    "Visa alla händelser",
    "Your shipment is delivered",
    "Your shipment has been delivered",
    "Försändelsen är levererad",
    "Försändelsen har levererats",
)

# Status keywords scanned in event text. Order matters: longer / more
# specific phrases first so "out for delivery" wins over "delivered".
_STATUS_KEYWORDS = (
    "out for delivery",
    "not loaded",
    "delivered",
    "collected",
    "departed",
    "arrived",
    "loaded",
    "booked",
    "picked up",
    "in transit",
)

_DATE_RE = re.compile(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4}")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_COUNTRY_RE = re.compile(r"\b([A-Z]{2})\b")
_ADDRESS_RE = re.compile(r"(\d{4,5})[,\s]+([^,\n]+?)(?:[,\s]+([A-Za-zÀ-ÿ\s]+))?$")
_WEIGHT_RE = re.compile(
    r"(?:weight|gross|vikt)[:\s]*(\d+(?:[.,]\d+)?)\s*(kg|KG|lbs?|t)?", re.IGNORECASE
)
_PIECES_RE = re.compile(
    r"(?:pieces?|pcs|qty|quantity|collis?|number of packages|antal\s+(?:kollin|paket))[:\s]*(\d+)",
    re.IGNORECASE,
)
_VOLUME_RE = re.compile(
    r"(?:volume|cbm|volym)[:\s]*(\d+(?:[.,]\d+)?)\s*(?:m3|m³|cbm)?", re.IGNORECASE
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
            from playwright.async_api import (
                Error as PlaywrightError,
            )
            from playwright.async_api import (
                async_playwright,
            )
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
                try:
                    await page.goto(
                        f"{self.SPA_URL}?refNumber={reference}",
                        wait_until="networkidle",
                    )
                    data = await page.evaluate(_EXTRACTION_SCRIPT)
                except PlaywrightError as e:
                    # Playwright timeouts + navigation errors all inherit
                    # from `playwright.async_api.Error`. Map to a domain
                    # error so the wire response stays in our taxonomy
                    # (`upstream_unavailable`) and the service-layer
                    # breaker counts it as a failure.
                    _log.warning(
                        "html_fallback.playwright_error",
                        reference=reference,
                        exc=type(e).__name__,
                    )
                    raise UpstreamUnavailableError(
                        "html fallback failed",
                        details={"reference": reference, "cause": type(e).__name__},
                    ) from e
            finally:
                await browser.close()

        body = str((data or {}).get("bodyText") or "")
        if any(marker in body for marker in NOT_FOUND_MARKERS):
            raise NotFoundError(
                "shipment not found (html fallback)", details={"reference": reference}
            )
        if not any(marker in body for marker in DETAIL_MARKERS):
            _log.warning(
                "html_fallback.no_detail_markers",
                reference=reference,
                body_preview=body[:120],
            )
            raise UpstreamUnavailableError(
                "html fallback could not load shipment detail",
                details={"reference": reference, "cause": "landing_or_empty"},
            )

        return _to_shipment(reference, data)


_EXTRACTION_SCRIPT = """
() => {
  const text = (sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  };
  const all = (sel) => Array.from(document.querySelectorAll(sel))
    .map(e => (e.textContent || "").trim())
    .filter(t => t.length > 0);
  // Rodram's broader selector list catches table-driven and timeline-driven
  // event renderings the SPA uses in different layouts.
  const eventNodes = all(
    "table tbody tr, [class*='event'], [class*='timeline'] > *, [class*='history'] li"
  );
  return {
    bodyText: document.body.innerText || "",
    senderName: text('[data-testid="sender-name"], .sender-name'),
    receiverName: text('[data-testid="receiver-name"], .receiver-name'),
    events: eventNodes,
  };
}
"""


def _section_between(text: str, start_label: str, end_labels: tuple[str, ...]) -> str | None:
    """Extract the substring between `start_label` and whichever of
    `end_labels` appears first afterwards. Case-insensitive. Mirrors
    rodram's `extractBetween` helper."""
    lower = text.lower()
    start_idx = lower.find(start_label.lower())
    if start_idx == -1:
        return None
    search_from = start_idx + len(start_label)
    end_idx = len(text)
    for end_label in end_labels:
        idx = lower.find(end_label.lower(), search_from)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    return text[search_from:end_idx].strip()


def _parse_address_line(line: str) -> dict[str, str | None]:
    """Parse a "<postal>, <city>, <country>" line. Tolerant of stray
    whitespace and missing country. Returns a dict with `postal_code`,
    `city`, `country` (any may be None)."""
    match = _ADDRESS_RE.search(line)
    if not match:
        return {"postal_code": None, "city": None, "country": None}
    return {
        "postal_code": match.group(1),
        "city": (match.group(2) or "").strip() or None,
        "country": (match.group(3) or "").strip() or None,
    }


def _extract_party(section: str | None) -> Party:
    """Parse a sender/receiver block into a `Party`. First non-empty
    line is the name; first line matching `\\d{4,5}` is the address."""
    if not section:
        return Party(name="", address=Address())
    lines = [s.strip() for s in section.splitlines() if s.strip()]
    if not lines:
        return Party(name="", address=Address())
    name = lines[0]
    addr_line = next((line for line in lines if re.search(r"\d{4,5}", line)), None)
    if addr_line is None:
        return Party(name=name, address=Address())
    parsed = _parse_address_line(addr_line)
    return Party(
        name=name,
        address=Address(
            street=None,
            postal_code=parsed["postal_code"],
            city=parsed["city"],
            country=parsed["country"],
        ),
    )


def _detect_status(text: str) -> str:
    """Return the first matching status keyword (capitalised) or ''."""
    lower = text.lower()
    for keyword in _STATUS_KEYWORDS:
        if keyword in lower:
            return keyword[0].upper() + keyword[1:]
    return ""


def _parse_datetime(date_str: str, time_str: str | None) -> datetime | None:
    """Parse a date string (e.g. '2025/12/18' or '18-12-2025') plus
    optional 'HH:MM' time into a UTC datetime. Returns None on
    unparseable input.

    Caveat: DSV doesn't expose timezone in the HTML view; we anchor at
    UTC so downstream sorting is consistent. A future per-locale
    timezone-mapping pass could refine this.
    """
    normalised = date_str.replace(".", "-").replace("/", "-")
    parts = normalised.split("-")
    if len(parts) != 3:
        return None
    try:
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    hour = minute = 0
    if time_str:
        try:
            hh, mm = time_str.split(":")
            hour, minute = int(hh), int(mm)
        except ValueError:
            pass
    try:
        return datetime(year, month, day, hour, minute, tzinfo=UTC)
    except ValueError:
        return None


def _parse_event_text(text: str) -> TrackingEvent | None:
    """Extract a `TrackingEvent` from a single line / row text blob.
    Returns None if no date is present (rodram's primary gating signal)."""
    if not text or not (10 <= len(text) <= 300):
        return None
    if "Items per page" in text or "Event Country Location" in text:
        return None
    date_match = _DATE_RE.search(text)
    if not date_match:
        return None
    time_match = _TIME_RE.search(text)
    when = _parse_datetime(date_match.group(0), time_match.group(0) if time_match else None)
    if when is None:
        return None
    status = _detect_status(text)
    if not status:
        # No matching keyword. Anchor on a non-empty status string so
        # the Pydantic schema accepts the event; "event" is intentionally
        # vague so it can't be confused with a known status.
        status = "event"
    country_match = _COUNTRY_RE.search(text)
    location = _extract_location(text, status, country_match.group(1) if country_match else None)
    description = re.sub(r"\s+", " ", text).strip()
    return TrackingEvent(
        at=when,
        location=location or None,
        status=status,
        description=description[:200] if description else None,
    )


def _extract_location(text: str, status: str, country_code: str | None) -> str:
    """Best-effort location extraction. Strips the matched status
    keyword and the country code from the text so the leftover is
    closer to a clean city name. Mirrors rodram's location-cleanup
    loop without its regex correctness pitfalls."""
    location = text
    if status:
        location = re.sub(re.escape(status), "", location, flags=re.IGNORECASE)
    if country_code:
        location = re.sub(rf"\b{re.escape(country_code)}\b", "", location)
    location = _DATE_RE.sub("", location)
    location = _TIME_RE.sub("", location)
    location = re.sub(r"\s+", " ", location).strip(" -,")
    # Prefer the last alphabetic word group as the city — postal/numeric
    # tokens are usually first; the city name tends to trail.
    pieces = [p for p in location.split() if p and not p.isdigit()]
    return " ".join(pieces[:3])  # cap to avoid scraping descriptions back in


def _extract_package(body: str) -> PackageInfo:
    """Pull weight, pieces, and volume from the body text. All optional."""
    weight_kg: Decimal | None = None
    weight_match = _WEIGHT_RE.search(body)
    if weight_match:
        raw_weight = weight_match.group(1).replace(",", ".")
        unit = (weight_match.group(2) or "kg").lower()
        try:
            kg = Decimal(raw_weight)
        except (ValueError, ArithmeticError):
            kg = None
        if kg is not None:
            if unit == "t":
                kg *= Decimal("1000")
            elif unit.startswith("lb"):
                kg *= Decimal("0.453592")
            weight_kg = kg.quantize(Decimal("0.01"))

    piece_count = 1
    pieces_match = _PIECES_RE.search(body)
    if pieces_match:
        try:
            piece_count = int(pieces_match.group(1))
        except ValueError:
            pass

    volume_m3: Decimal | None = None
    volume_match = _VOLUME_RE.search(body)
    if volume_match:
        try:
            volume_m3 = Decimal(volume_match.group(1).replace(",", "."))
        except (ValueError, ArithmeticError):
            volume_m3 = None

    return PackageInfo(
        weight_kg=weight_kg,
        length_cm=None,
        width_cm=None,
        height_cm=None,
        piece_count=piece_count,
        volume_m3=volume_m3,
    )


def _dedupe_and_sort(events: list[TrackingEvent]) -> list[TrackingEvent]:
    """Drop duplicates keyed on (at, status); sort newest first."""
    seen: set[tuple[datetime, str]] = set()
    deduped: list[TrackingEvent] = []
    for event in events:
        key = (event.at, event.status)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    deduped.sort(key=lambda e: e.at, reverse=True)
    return deduped[:30]


def _to_shipment(reference: str, data: dict[str, Any]) -> Shipment:
    """Map the scraped data to a `Shipment`. Conservative — best-effort fields.

    Structured-event extraction (ported from rodram/shipmentTrackerMCP's
    parser.ts, 2026-05-16): each event row is regex-parsed for date,
    time, country, location, status. Falls back to line-by-line scan of
    the body text when DOM selectors yield nothing.
    """
    type_hint: ShipmentType = "unknown"
    body = str(data.get("bodyText") or "")

    # Sender / receiver: prefer DOM-selector hits (the SPA may expose
    # data-testids), otherwise extract from labelled body sections.
    sender_name_dom = data.get("senderName")
    receiver_name_dom = data.get("receiverName")
    if sender_name_dom:
        sender = Party(name=str(sender_name_dom), address=Address())
    else:
        sender_section = _section_between(
            body, "Sender", ("Receiver", "Consignee", "Package", "Shipment", "Weight")
        )
        sender = _extract_party(sender_section)
    if receiver_name_dom:
        receiver = Party(name=str(receiver_name_dom), address=Address())
    else:
        receiver_section = _section_between(
            body, "Receiver", ("Package", "Shipment", "Weight", "Details", "History", "Events")
        ) or _section_between(
            body, "Consignee", ("Package", "Shipment", "Weight", "Details", "History", "Events")
        )
        receiver = _extract_party(receiver_section)

    package = _extract_package(body)

    # Events: DOM rows first, body lines as fallback (rodram's pattern).
    raw_events = data.get("events") or []
    parsed_events: list[TrackingEvent] = []
    for raw in raw_events:
        event = _parse_event_text(str(raw))
        if event is not None:
            parsed_events.append(event)
    if not parsed_events and body:
        for line in body.splitlines():
            event = _parse_event_text(line.strip())
            if event is not None:
                parsed_events.append(event)

    history = _dedupe_and_sort(parsed_events)
    return Shipment(
        reference=reference,
        type=type_hint,
        sender=sender,
        receiver=receiver,
        package=package,
        history=history,
        source="html_fallback",
    )
