"""Shared time utilities."""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current time in UTC (timezone-aware)."""
    return datetime.now(timezone.utc)
