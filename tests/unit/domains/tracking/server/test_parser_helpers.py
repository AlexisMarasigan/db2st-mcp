"""Direct tests for the parser's low-level coercion helpers.

These previously had coverage only through `parse_detail`, which makes
regressions hard to localize. Each helper is intentionally lenient about
upstream junk (None, empty strings, malformed values) and that contract
needs its own pinning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

import db2st_mcp.domains.tracking.server.parser as parser_module
from db2st_mcp.domains.tracking.server.parser import _classify

# --- _decimal ---------------------------------------------------------------


class TestDecimalHelper:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.4", Decimal("12.4")),
            (12, Decimal("12")),
            (12.4, Decimal("12.4")),
            ("0", Decimal("0")),
        ],
    )
    def test_parses_valid_values(self, raw: object, expected: Decimal) -> None:
        assert parser_module._decimal(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "wat", "12.4abc"])
    def test_returns_none_for_junk(self, raw: object) -> None:
        assert parser_module._decimal(raw) is None


# --- _int -------------------------------------------------------------------


class TestIntHelper:
    @pytest.mark.parametrize(("raw", "expected"), [("3", 3), (3, 3), ("0", 0)])
    def test_parses_valid_values(self, raw: object, expected: int) -> None:
        assert parser_module._int(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "wat", 3.5])
    def test_returns_none_for_junk(self, raw: object) -> None:
        # Floats coerce to int via int(); we accept that (matches upstream).
        if isinstance(raw, float):
            assert parser_module._int(raw) == int(raw)
        else:
            assert parser_module._int(raw) is None


# --- _str -------------------------------------------------------------------


class TestStrHelper:
    @pytest.mark.parametrize(("raw", "expected"), [("hi", "hi"), ("  hi  ", "hi"), (42, "42")])
    def test_parses_valid_values(self, raw: object, expected: str) -> None:
        assert parser_module._str(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_returns_none_for_empty(self, raw: object) -> None:
        assert parser_module._str(raw) is None


# --- _datetime --------------------------------------------------------------


class TestDatetimeHelper:
    def test_iso_with_z_suffix(self) -> None:
        got = parser_module._datetime("2026-05-15T10:00:00Z")
        assert got == datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)

    def test_iso_with_timezone_offset(self) -> None:
        got = parser_module._datetime("2026-05-15T12:00:00+02:00")
        assert got is not None
        assert got.utcoffset() is not None
        assert got.astimezone(UTC) == datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)

    def test_passes_through_existing_datetime(self) -> None:
        original = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)
        assert parser_module._datetime(original) is original

    @pytest.mark.parametrize("raw", [None, "", "yesterday", "2026-13-99"])
    def test_returns_none_for_junk(self, raw: object) -> None:
        assert parser_module._datetime(raw) is None


# --- _classify --------------------------------------------------------------


class TestClassifyHelper:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("land_se", "land_se"),
            ("se", "land_se"),
            ("Sweden", "land_se"),
            ("AU", "land_au"),
            ("nz", "land_au"),
            ("domestic_au_nz", "land_au"),
            ("LAND", "land"),
            ("ocean", "ocean"),
            ("sea", "ocean"),
            ("Air", "air"),
            ("DSV", "dsv"),
            ("atol", "atol"),
            ("cos", "cos"),
        ],
    )
    def test_known_types(self, raw: str, expected: str) -> None:
        assert _classify(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "  ", "what_is_this"])
    def test_unknown_falls_through(self, raw: object) -> None:
        assert _classify(raw) == "unknown"
