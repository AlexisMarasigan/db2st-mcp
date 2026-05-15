"""tracking-domain Pydantic models.

These are the contract between the MCP tool, the upstream client, and the
parser. The tool output schema is derived from `Shipment`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShipmentType = Literal[
    "land",
    "land_se",
    "land_au",
    "ocean",
    "air",
    "dsv",
    "atol",
    "cos",
    "unknown",
]


class Address(BaseModel):
    """Postal address. Optional fields tolerate partial upstream data."""

    model_config = ConfigDict(extra="forbid")

    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None  # ISO 3166-1 alpha-2 when available


class Party(BaseModel):
    """A sender or receiver."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    address: Address = Field(default_factory=Address)


class PackageInfo(BaseModel):
    """Package metadata. Fields optional; not every shipment exposes everything."""

    model_config = ConfigDict(extra="forbid")

    weight_kg: Decimal | None = None
    length_cm: int | None = None
    width_cm: int | None = None
    height_cm: int | None = None
    piece_count: int = 1
    volume_m3: Decimal | None = None


class TrackingEvent(BaseModel):
    """A single point in the shipment timeline."""

    model_config = ConfigDict(extra="forbid")

    at: datetime
    location: str | None = None
    status: str
    description: str | None = None


class Shipment(BaseModel):
    """Top-level shipment record returned by the `track_shipment` tool."""

    model_config = ConfigDict(extra="forbid")

    reference: str
    type: ShipmentType = "unknown"
    sender: Party = Field(default_factory=Party)
    receiver: Party = Field(default_factory=Party)
    package: PackageInfo = Field(default_factory=PackageInfo)
    history: list[TrackingEvent] = Field(default_factory=list)
    source: Literal["json", "html_fallback"] = "json"
