"""Time helpers. Every timestamp is UTC (engineering standard 15, ADR-0021)."""

from __future__ import annotations

from datetime import UTC, datetime


def require_utc(moment: datetime, name: str) -> datetime:
    """Return the moment in UTC as a plain datetime. Refuse a naive one, its zone is unknown.

    A scheduled Airflow run hands over pendulum.DateTime, a datetime subclass. Spark cannot
    infer a type for it, and once its zone is the standard library's UTC, pendulum drops the
    zone in arithmetic. Rebuilding a plain datetime keeps both problems out of my code.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware (UTC), got a naive datetime")
    utc = moment.astimezone(UTC)
    return datetime.combine(utc.date(), utc.time(), tzinfo=UTC)


def format_utc(moment: datetime) -> str:
    """Format an aware datetime as an ISO 8601 UTC string ending in Z."""
    return require_utc(moment, "moment").strftime("%Y-%m-%dT%H:%M:%SZ")
