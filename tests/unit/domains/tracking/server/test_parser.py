"""Unit tests for the tracking-domain parser.

Fixtures are hand-crafted to match the shapes observed from the DSV bundle:
- resolver returns a list (or a `{shipments: [...]}` wrapper)
- detail returns a typed object with sender/receiver/package/history
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from db2st_mcp.domains.tracking.server.parser import (
    parse_detail,
    parse_resolver,
)
from db2st_mcp.domains.tracking.shared.schemas import (
    Shipment,
)
from db2st_mcp.shared.errors import ParseError

# --- resolver ---------------------------------------------------------------


class TestParseResolver:
    def test_extracts_first_candidate_from_list(self) -> None:
        candidates = parse_resolver(
            [
                {"id": "1806203236", "type": "land_se"},
                {"id": "1806203236", "type": "land"},
            ]
        )
        assert candidates == [("land_se", "1806203236"), ("land", "1806203236")]

    def test_accepts_wrapper_object(self) -> None:
        candidates = parse_resolver({"shipments": [{"id": "X", "type": "ocean"}]})
        assert candidates == [("ocean", "X")]

    def test_classifies_unknown_type(self) -> None:
        candidates = parse_resolver([{"id": "X", "type": "wat"}])
        assert candidates == [("unknown", "X")]

    def test_skips_items_without_id(self) -> None:
        candidates = parse_resolver([{"type": "land"}, {"id": "Y", "type": "air"}])
        assert candidates == [("air", "Y")]

    def test_raises_parse_error_on_non_list(self) -> None:
        with pytest.raises(ParseError):
            parse_resolver({"shipments": "nope"})  # type: ignore[arg-type]


# --- detail -----------------------------------------------------------------


@pytest.fixture
def land_se_payload() -> dict[str, object]:
    return {
        "sender": {
            "name": "Acme AB",
            "address": {
                "street": "Storgatan 1",
                "postalCode": "11122",
                "city": "Stockholm",
                "country": "SE",
            },
        },
        "receiver": {
            "name": "Globex GmbH",
            "address": {
                "street": "Hauptstr. 5",
                "postalCode": "10115",
                "city": "Berlin",
                "country": "DE",
            },
        },
        "package": {
            "weight": "12.4",
            "pieceCount": 2,
            "dimensions": {"length": 60, "width": 40, "height": 30},
            "volume": "0.072",
        },
        "events": [
            {
                "timestamp": "2026-05-12T08:15:00Z",
                "location": "Stockholm",
                "status": "PICKED_UP",
                "description": "Picked up at sender",
            },
            {
                "timestamp": "2026-05-13T22:40:00Z",
                "location": "Malmö",
                "status": "IN_TRANSIT",
                "description": "Departed terminal",
            },
            {
                "timestamp": "2026-05-15T09:05:00+02:00",
                "location": "Berlin",
                "status": "DELIVERED",
            },
        ],
    }


class TestParseDetail:
    def test_full_payload_round_trips_to_shipment(self, land_se_payload: dict[str, object]) -> None:
        shipment: Shipment = parse_detail("1806203236", "land_se", land_se_payload)

        assert shipment.reference == "1806203236"
        assert shipment.type == "land_se"
        assert shipment.source == "json"
        assert shipment.sender.name == "Acme AB"
        assert shipment.sender.address.country == "SE"
        assert shipment.receiver.address.city == "Berlin"
        assert shipment.package.weight_kg == Decimal("12.4")
        assert shipment.package.piece_count == 2
        assert shipment.package.length_cm == 60
        assert shipment.package.volume_m3 == Decimal("0.072")
        assert len(shipment.history) == 3

    def test_events_are_sorted_chronologically(self, land_se_payload: dict[str, object]) -> None:
        shipment = parse_detail("X", "land_se", land_se_payload)
        timestamps = [e.at for e in shipment.history]
        assert timestamps == sorted(timestamps)

    def test_tolerates_missing_party(self) -> None:
        shipment = parse_detail("X", "land", {"package": {"pieceCount": 1}})
        assert shipment.sender.name == ""
        assert shipment.receiver.name == ""

    def test_drops_events_without_timestamp(self) -> None:
        shipment = parse_detail(
            "X",
            "land",
            {"events": [{"status": "FOO"}, {"timestamp": "2026-05-15T10:00:00Z", "status": "BAR"}]},
        )
        assert len(shipment.history) == 1
        assert shipment.history[0].status == "BAR"

    def test_handles_z_suffix_timestamps(self) -> None:
        shipment = parse_detail(
            "X",
            "land",
            {"events": [{"timestamp": "2026-05-15T10:00:00Z", "status": "OK"}]},
        )
        assert shipment.history[0].at == datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)

    def test_raises_parse_error_on_non_dict(self) -> None:
        with pytest.raises(ParseError):
            parse_detail("X", "land", "nope")  # type: ignore[arg-type]
