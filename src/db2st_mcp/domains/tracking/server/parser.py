"""Parse DSV/Schenker tracking JSON responses into the domain `Shipment`.

The upstream is a federation: one resolver endpoint returns a *summary*
(type + ids), then one of several detail endpoints returns the full record
in a type-specific shape. This module owns all of that translation.

Schema drift is the most likely failure mode; the parser is intentionally
defensive and surfaces missing pieces as `None` rather than failing.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from db2st_mcp.domains.tracking.shared.schemas import (
    Address,
    PackageInfo,
    Party,
    Shipment,
    ShipmentType,
    TrackingEvent,
)
from db2st_mcp.shared.errors import ParseError

JsonObj = dict[str, Any]


# --- low-level helpers -------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    # DSV emits ISO8601 with a trailing 'Z'. Python's fromisoformat handles
    # 'Z' from 3.11+. Fall back to stripping it for older formats.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# --- resolver ----------------------------------------------------------------


def parse_resolver(payload: JsonObj | list[JsonObj]) -> list[tuple[ShipmentType, str]]:
    """Parse `GET /tracking-public/shipments?query=<ref>`.

    Returns a list of `(type, id)` tuples. The first is the preferred
    detail endpoint; the rest are fallbacks if it 404s.
    """
    items = (
        payload
        if isinstance(payload, list)
        else payload.get("shipments", []) or payload.get("items", [])
    )
    if not isinstance(items, list):
        raise ParseError("resolver payload not a list", details={"got": type(items).__name__})

    out: list[tuple[ShipmentType, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        type_hint = _classify(item.get("type") or item.get("shipmentType") or item.get("transport"))
        ref = _str(item.get("id") or item.get("reference") or item.get("shipmentId"))
        if ref:
            out.append((type_hint, ref))
    return out


def _classify(raw: Any) -> ShipmentType:
    if raw is None:
        return "unknown"
    s = str(raw).strip().lower()
    if s in {"land_se", "se", "sweden"}:
        return "land_se"
    if s in {"land_au", "au", "nz", "domestic_au_nz"}:
        return "land_au"
    if s in {"land"}:
        return "land"
    if s in {"ocean", "sea"}:
        return "ocean"
    if s in {"air"}:
        return "air"
    if s in {"dsv"}:
        return "dsv"
    if s in {"atol"}:
        return "atol"
    if s in {"cos"}:
        return "cos"
    return "unknown"


# --- details -----------------------------------------------------------------


def parse_detail(
    reference: str,
    type_hint: ShipmentType,
    payload: JsonObj,
) -> Shipment:
    """Translate a type-specific detail payload into a `Shipment`."""
    if not isinstance(payload, dict):
        raise ParseError("detail payload not an object", details={"got": type(payload).__name__})

    sender = _party(payload.get("sender") or payload.get("from") or payload.get("consignor") or {})
    receiver = _party(
        payload.get("receiver") or payload.get("to") or payload.get("consignee") or {}
    )
    package = _package(payload)
    history = _history(payload)
    return Shipment(
        reference=reference,
        type=type_hint,
        sender=sender,
        receiver=receiver,
        package=package,
        history=history,
        source="json",
    )


def _party(node: Any) -> Party:
    if not isinstance(node, dict):
        return Party()
    name = _str(node.get("name") or node.get("companyName")) or ""
    return Party(name=name, address=_address(node))


def _address(node: JsonObj) -> Address:
    inner = node.get("address") if isinstance(node.get("address"), dict) else node
    if not isinstance(inner, dict):
        return Address()
    return Address(
        street=_str(inner.get("street") or inner.get("addressLine1") or inner.get("addressLine")),
        postal_code=_str(inner.get("postalCode") or inner.get("zipCode")),
        city=_str(inner.get("city")),
        country=_str(inner.get("country") or inner.get("countryCode")),
    )


def _package(node: JsonObj) -> PackageInfo:
    pkg = node.get("package") or node.get("goods") or {}
    if not isinstance(pkg, dict):
        pkg = {}

    dims = pkg.get("dimensions") or {}
    if not isinstance(dims, dict):
        dims = {}

    piece_count = _int(pkg.get("pieceCount") or pkg.get("pieces") or pkg.get("colli")) or 1
    return PackageInfo(
        weight_kg=_decimal(pkg.get("weight") or pkg.get("weightKg")),
        length_cm=_int(dims.get("length") or pkg.get("length")),
        width_cm=_int(dims.get("width") or pkg.get("width")),
        height_cm=_int(dims.get("height") or pkg.get("height")),
        piece_count=piece_count,
        volume_m3=_decimal(pkg.get("volume") or pkg.get("volumeM3")),
    )


def _history(node: JsonObj) -> list[TrackingEvent]:
    raw = (
        node.get("events")
        or node.get("history")
        or node.get("trackingEvents")
        or node.get("statusHistory")
        or []
    )
    if not isinstance(raw, list):
        return []
    out: list[TrackingEvent] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        at = _datetime(entry.get("at") or entry.get("timestamp") or entry.get("eventTime"))
        if at is None:
            continue
        status = (
            _str(entry.get("status") or entry.get("statusCode") or entry.get("type")) or "unknown"
        )
        out.append(
            TrackingEvent(
                at=at,
                location=_str(entry.get("location") or entry.get("place") or entry.get("city")),
                status=status,
                description=_str(
                    entry.get("description") or entry.get("statusDescription") or entry.get("text")
                ),
            )
        )
    out.sort(key=lambda e: e.at)
    return out
