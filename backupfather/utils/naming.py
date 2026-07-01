"""Filesystem-safe backup filename generation."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def utc_timestamp(now: datetime | None = None) -> str:
    """Return a filesystem-safe UTC timestamp, e.g. ``2026-07-01T03-00-00Z``."""
    now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    return now.strftime("%Y-%m-%dT%H-%M-%SZ")


def sanitize(component: str) -> str:
    """Replace anything unsafe for a filename with an underscore."""
    return _SAFE.sub("_", component)


def build_filename(db_name: str, extension: str, now: datetime | None = None) -> str:
    """Build ``<db>_<timestamp><extension>`` (extension includes the dot).

    Example: ``build_filename("taxpanel_prod", ".dump")`` ->
    ``taxpanel_prod_2026-07-01T03-00-00Z.dump``.
    """
    return f"{sanitize(db_name)}_{utc_timestamp(now)}{extension}"
