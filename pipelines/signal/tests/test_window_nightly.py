"""Tests for the nightly satellite window step (C5): what it reads, when it stops, what it writes.

It reads the run date's selected satellites and the newest trail points with their horizons,
checks the row limit before anything is written, and writes the run date's partition. Spark is a
fake that answers those reads and runs the job's partitions in this process.
"""

from dataclasses import asdict, fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sample_iceberg_job import CATALOG_NAME
from satellite_windows import SPAN_MINUTES, WINDOW_COLUMNS, RowLimitExceeded
from signal_nightly import compute_windows
from test_window_job import HORIZONS, POINTS, SATELLITES
from test_window_job import FakeSpark as JobSpark
from trail_loader import TrailPoint

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NAMESPACE = "portfolio_dev"
RUN_DATE = date(2026, 11, 4)
SPAN_START = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
STARTED = datetime(2026, 11, 4, 10, 0, 40, tzinfo=UTC)
NOW = datetime(2026, 11, 4, 10, 20, tzinfo=UTC)
DTC = f"{CATALOG_NAME}.{NAMESPACE}.dtc_satellite"
POINTS_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point"
HORIZONS_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point_horizon"
WINDOWS_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.satellite_window"


class Frame:
    """Stands in for the job's DataFrame: it can be cached, counted and written."""

    def __init__(self, spark, rows):
        self.spark, self.rows = spark, rows

    def persist(self):
        self.spark.calls.append("persist")
        return self

    def unpersist(self):
        self.spark.calls.append("unpersist")
        return self

    def count(self):
        return len(self.rows)

    def writeTo(self, name):  # noqa: N802, Spark method name
        frame = self

        class Writer:
            def partitionedBy(self, column):  # noqa: N802, Spark method name
                return self

            def create(self):
                frame.spark.written[name] = frame.rows

            def overwritePartitions(self):  # noqa: N802, Spark method name
                frame.spark.written[name] = frame.rows

        return Writer()


class FakeSpark(JobSpark):
    """Answers the step's reads from the lake and keeps what it writes."""

    def __init__(
        self, *, dtc_rows=True, points_date=RUN_DATE, horizons_date=RUN_DATE, windows=False
    ):
        super().__init__()
        self.dtc_rows = (
            [asdict(s) | {"perigee_km": 340.0, "apogee_km": 342.0} for s in SATELLITES]
            if dtc_rows
            else []
        )
        self.dates = {POINTS_TABLE: points_date, HORIZONS_TABLE: horizons_date}
        self.tables = {DTC, WINDOWS_TABLE} if windows else {DTC}
        self.tables |= {name for name, value in self.dates.items() if value is not None}
        self.written = {}
        self.calls = []
        self.queries = []
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return name in spark.tables

        self.catalog = Catalog()

    def sql(self, statement):
        self.queries.append(statement)
        if "MAX(run_date)" in statement:
            table = (
                POINTS_TABLE
                if POINTS_TABLE in statement and HORIZONS_TABLE not in statement
                else HORIZONS_TABLE
            )
            rows = [{"newest": self.dates[table]}]
        elif DTC in statement:
            rows = self.dtc_rows
        elif HORIZONS_TABLE in statement:
            rows = [
                {"trail_point_id": k, "horizon_angles_deg": list(v.angles_deg)}
                for k, v in HORIZONS.items()
            ]
        else:
            names = [f.name for f in fields(TrailPoint)]
            rows = [{n: getattr(p, n) for n in names} for p in POINTS]
        return type("Result", (), {"collect": lambda _self: rows})()

    def createDataFrame(self, rdd, schema=None):  # noqa: N802, Spark method name
        super().createDataFrame(rdd, schema)
        return Frame(self, self.frames[-1]["rows"])


def run(spark, **overrides):
    arguments = {
        "contracts_dir": CONTRACTS,
        "namespace": NAMESPACE,
        "span_start_utc": SPAN_START,
        "run_started_utc": STARTED,
        "now_utc": NOW,
    } | overrides
    return compute_windows(spark, RUN_DATE, **arguments)


def test_the_step_writes_the_run_date_partition_and_reports_its_counts():
    spark = FakeSpark()
    result = run(spark)
    rows = spark.written[WINDOWS_TABLE]
    assert result == {"satellites": len(SATELLITES), "points": len(POINTS), "windows": len(rows)}
    assert len(rows) > 0
    values = dict(zip(WINDOW_COLUMNS, rows[0], strict=True))
    assert values["run_date"] == RUN_DATE
    assert values["valid_until_utc"] == SPAN_START + timedelta(minutes=SPAN_MINUTES)
    assert values["run_started_utc"] == STARTED
    assert values["loaded_at_utc"] == NOW


def test_the_satellites_are_the_run_dates_selection():
    spark = FakeSpark()
    run(spark)
    (query,) = [q for q in spark.queries if DTC in q]
    assert "run_date = DATE '2026-11-04'" in query


def test_the_windows_are_counted_once_from_a_cached_frame_and_the_cache_is_freed():
    spark = FakeSpark()
    run(spark)
    assert spark.calls == ["persist", "unpersist"]


def test_a_run_over_the_row_limit_writes_nothing():
    spark = FakeSpark()
    with pytest.raises(RowLimitExceeded):
        run(spark, max_rows=1)
    assert spark.written == {}
    assert spark.calls == ["persist", "unpersist"]


def test_a_rerun_of_the_day_overwrites_its_partition():
    spark = FakeSpark(windows=True)
    run(spark)
    assert WINDOWS_TABLE in spark.written


def test_no_selected_satellites_stops_the_step():
    with pytest.raises(ValueError, match="dtc_satellite"):
        run(FakeSpark(dtc_rows=False))


def test_no_trail_points_stops_the_step():
    with pytest.raises(ValueError, match="trail points"):
        run(FakeSpark(points_date=None))


def test_no_horizons_stops_the_step():
    with pytest.raises(ValueError, match="horizon"):
        run(FakeSpark(horizons_date=None))


def test_horizons_older_than_the_trail_points_stop_the_step():
    with pytest.raises(ValueError, match="older"):
        run(FakeSpark(points_date=RUN_DATE, horizons_date=RUN_DATE - timedelta(days=1)))
