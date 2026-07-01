"""Tests for backup filename generation."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from backupfather.utils.naming import build_filename, sanitize, utc_timestamp


def test_utc_timestamp_format() -> None:
    dt = datetime(2026, 7, 1, 3, 0, 0, tzinfo=UTC)
    assert utc_timestamp(dt) == "2026-07-01T03-00-00Z"


def test_utc_timestamp_converts_to_utc() -> None:
    # A non-UTC tz must be normalized to UTC before formatting.
    from datetime import timedelta

    tehran = timezone(timedelta(hours=3, minutes=30))
    dt = datetime(2026, 7, 1, 6, 30, 0, tzinfo=tehran)  # == 03:00 UTC
    assert utc_timestamp(dt) == "2026-07-01T03-00-00Z"


def test_build_filename() -> None:
    dt = datetime(2026, 7, 1, 3, 0, 0, tzinfo=UTC)
    assert build_filename("taxpanel_prod", ".dump", dt) == "taxpanel_prod_2026-07-01T03-00-00Z.dump"


def test_sanitize_strips_unsafe_chars() -> None:
    assert sanitize("a/b c:d") == "a_b_c_d"
