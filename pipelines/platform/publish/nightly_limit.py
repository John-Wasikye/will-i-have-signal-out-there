"""The two-hour maximum for the nightly run.

The nightly run may take about 45 minutes, and it has a hard maximum of 2 hours. When a run
reaches the maximum, the box watchdog stops the box and records an incident, so the next run
catches up.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from timeutil import require_utc

NIGHTLY_MAXIMUM = timedelta(hours=2)


def reached_maximum(started_utc: datetime, now_utc: datetime) -> bool:
    """Return True when the run has lasted as long as the maximum or longer."""
    started = require_utc(started_utc, "started_utc")
    now = require_utc(now_utc, "now_utc")
    return now - started >= NIGHTLY_MAXIMUM
