"""Datetime helpers used across the backend."""

from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> datetime:
    """Return a UTC timestamp for persistence."""
    return datetime.now(timezone.utc)


def format_dt(value: Optional[Any]) -> Optional[str]:
    """Format a datetime-like value for JSON responses."""
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
