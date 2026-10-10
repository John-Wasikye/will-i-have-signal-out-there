"""The two-hour maximum for the nightly run, and the incident it opens.

The nightly run may take about 45 minutes, and it has a hard maximum of 2 hours. When
a run reaches the maximum, I record an incident, so the next run catches up.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from incidents import build_incident
from timeutil import require_utc

NIGHTLY_MAXIMUM = timedelta(hours=2)


def reached_maximum(started_utc: datetime, now_utc: datetime) -> bool:
    """Return True when the run has lasted as long as the maximum or longer."""
    started = require_utc(started_utc, "started_utc")
    now = require_utc(now_utc, "now_utc")
    return now - started >= NIGHTLY_MAXIMUM


def build_maximum_incident(number: int, opened_utc: datetime, pipeline: str) -> dict:
    """Build the incident record for a run that reached the maximum."""
    return build_incident(
        number=number,
        opened_utc=opened_utc,
        pipeline=pipeline,
        what_broke="The nightly run reached its 2 hour maximum before it finished.",
        reached_maximum_runtime=True,
    )
