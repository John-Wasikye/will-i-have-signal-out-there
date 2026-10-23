"""Tests for the two-hour nightly maximum.

The rule comes from the build plan: the nightly run has a hard maximum of 2 hours, and
reaching it is recorded as an incident, so the next run can catch up.
"""

from datetime import UTC, datetime, timedelta

import pytest
from nightly_limit import NIGHTLY_MAXIMUM, reached_maximum

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
