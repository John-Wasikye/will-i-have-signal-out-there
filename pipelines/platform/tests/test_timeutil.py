"""Tests for the UTC helpers that every task uses on the times Airflow hands it."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from timeutil import require_utc


class AirflowTime(datetime):
    """Stands in for pendulum.DateTime, the datetime subclass a scheduled run gets from Airflow."""


def test_a_datetime_subclass_comes_back_as_a_plain_datetime():
    moment = require_utc(AirflowTime(2026, 10, 29, 10, 0, tzinfo=UTC), "now_utc")
    assert type(moment) is datetime
    assert moment == datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


def test_another_zone_is_converted_to_utc():
    eastern = timezone(timedelta(hours=-4))
    moment = require_utc(datetime(2026, 10, 29, 6, 0, 30, 123456, tzinfo=eastern), "now_utc")
    assert moment == datetime(2026, 10, 29, 10, 0, 30, 123456, tzinfo=UTC)
    assert moment.tzinfo is UTC


def test_a_naive_time_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        require_utc(datetime(2026, 10, 29, 10, 0), "now_utc")


def test_a_scheduled_runs_time_keeps_its_zone_after_arithmetic():
    pendulum = pytest.importorskip("pendulum", reason="pendulum comes with Airflow")
    moment = require_utc(pendulum.datetime(2026, 10, 29, 10, tz="UTC"), "now_utc")
    assert (moment - timedelta(hours=24)).tzinfo is UTC
