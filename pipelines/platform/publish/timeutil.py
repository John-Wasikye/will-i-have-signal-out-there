"""Time helpers. Every timestamp is UTC (engineering standard 15, ADR-0021)."""

from __future__ import annotations

from datetime import UTC, datetime


def require_utc(moment: datetime, name: str) -> datetime:
    """Return the moment in UTC. Refuse a naive datetime, because its zone is unknown."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware (UTC), got a naive datetime")
    return moment.astimezone(UTC)


def format_utc(moment: datetime) -> str:
    """Format an aware datetime as an ISO 8601 UTC string ending in Z."""
    return require_utc(moment, "moment").strftime("%Y-%m-%dT%H:%M:%SZ")
