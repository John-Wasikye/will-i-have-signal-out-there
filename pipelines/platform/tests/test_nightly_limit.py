"""Tests for the two-hour nightly maximum and the incident it opens.

The rule comes from the build plan: the nightly run has a hard maximum of 2 hours, and
reaching it is recorded as an incident, so the next run can catch up.
"""

from datetime import UTC, datetime, timedelta

import pytest
from nightly_limit import NIGHTLY_MAXIMUM, build_maximum_incident, reached_maximum

START = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)


def test_the_maximum_is_two_hours():
    assert NIGHTLY_MAXIMUM == timedelta(hours=2)


def test_a_run_under_two_hours_has_not_reached_the_maximum():
    assert reached_maximum(START, START + timedelta(minutes=45)) is False


def test_a_run_at_exactly_two_hours_has_reached_the_maximum():
    assert reached_maximum(START, START + timedelta(hours=2)) is True


def test_a_run_over_two_hours_has_reached_the_maximum():
    assert reached_maximum(START, START + timedelta(hours=3)) is True


def test_naive_times_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        reached_maximum(datetime(2026, 10, 10, 10, 0), START)


def test_the_incident_records_the_pipeline_and_the_maximum():
    incident = build_maximum_incident(
        number=1,
        opened_utc=START + timedelta(hours=2),
        pipeline="platform_skeleton_nightly",
    )
    assert incident["incident_id"] == "INC-2026-10-10-01"
    assert incident["opened_at_utc"] == "2026-10-10T12:00:00Z"
    assert incident["project"] == "platform"
    assert incident["pipeline"] == "platform_skeleton_nightly"
    assert incident["reached_maximum_runtime"] is True
    assert incident["status"] == "open"
    assert "2 hour" in incident["what_broke"]


def test_the_incident_number_is_two_digits():
    incident = build_maximum_incident(
        number=12,
        opened_utc=START + timedelta(hours=2),
        pipeline="platform_skeleton_nightly",
    )
    assert incident["incident_id"] == "INC-2026-10-10-12"


def test_the_incident_refuses_a_naive_opened_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_maximum_incident(
            number=1,
            opened_utc=datetime(2026, 10, 10, 12, 0),
            pipeline="platform_skeleton_nightly",
        )
