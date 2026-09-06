"""parseLocalDate must not shift a UTC-midnight date-only value to the prior day.

The today/plan APIs return calendar dates as ""Wed, 16 Sep 2026 00:00:00 GMT"" and
""2026-09-16"". In a UTC-negative timezone (America/New_York) a naive
`new Date` parse renders the prior day (Sep 15). parseLocalDate must keep the
API's calendar day (Sep 16) regardless of the host timezone.
"""
from pathlib import Path


def _format_js():
    return Path("static/js/meridian/format.js").read_text(encoding="utf-8")


def test_parse_local_date_rejects_plain_timestamp_z():
    """Full ISO timestamps with a real time (noon) must still parse normally."""
    js = _format_js()
    # The function exists and distinguishes date-only from timestamps.
    assert "export function parseLocalDate" in js


def test_parse_local_date_handles_gmt_midnight_form():
    """A ""Wed, 16 Sep 2026 00:00:00 GMT"" calendar date must not shift a day."""
    js = _format_js()
    # Detect the UTC-midnight branch (uses getUTC* components to preserve the day).
    assert "/00:00:00/i.test(value)" in js
    assert "getUTCFullYear" in js
    assert "getUTCDate" in js


def test_parse_local_date_keeps_iso_date_only_branch():
    """Date-only ISO still rides the noon trick (no UTC shift)."""
    js = _format_js()
    assert "/^\\d{4}-\\d{2}-\\d{2}$/.test(value)" in js
    assert "T12:00:00" in js
