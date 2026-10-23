"""Sample rows for the walking skeleton. Pure Python, shared by Spark and the publish flow."""

from __future__ import annotations

from datetime import date, datetime

from timeutil import require_utc

FRESHNESS_TARGET_HOURS = 26.0

_SAMPLE_ROWS = (
    ("hello", "The skeleton is live."),
    ("iceberg", "This row went through Spark and Iceberg."),
    ("duckdb", "This row is served from Parquet by DuckDB."),
)


def build_sample_rows(now_utc: datetime, run_date: date) -> list[dict]:
    """Return the sample rows for one run. Every row carries the run's UTC time."""
    now_utc = require_utc(now_utc, "now_utc")
    return [
        {
            "key": key,
            "value": value,
            "last_good_run_utc": now_utc,
            "freshness_target_hours": FRESHNESS_TARGET_HOURS,
            "run_date": run_date,
        }
        for key, value in _SAMPLE_ROWS
    ]
