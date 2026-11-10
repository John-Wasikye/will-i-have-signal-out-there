"""Tests for the step that copies lake tables to plain Parquet for dbt (C7, OQ-40).

dbt on DuckDB does not read Iceberg, so Spark copies only the partitions tonight's models use.
Trail points and coverage are reference data, so their newest partitions count (ADR 0028). The
windows must be tonight's. No test here starts Spark; test_dbt_copy_spark.py does.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sample_iceberg_job import CATALOG_NAME
from signal_nightly import copy_tables_for_dbt

RUN_DATE = date(2026, 11, 5)
RUN_TIME = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
NAMESPACE = "portfolio_dev"
POINTS = f"{CATALOG_NAME}.{NAMESPACE}.trail_point"
COVERAGE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point_coverage"
WINDOWS = f"{CATALOG_NAME}.{NAMESPACE}.satellite_window"
REPORTS = f"{CATALOG_NAME}.{NAMESPACE}.signal_report"


class FakeFrame:
    """Records where a query's rows were written."""

    def __init__(self, spark, query):
        self.spark, self.query = spark, query

    def coalesce(self, _partitions):
        return self

    @property
    def write(self):
        return self

    def mode(self, mode):
        assert mode == "overwrite"
        return self

    def parquet(self, path):
        self.spark.copied[Path(path).name] = self.query

    def collect(self):
        if "MAX(run_date)" in self.query:
            newest = next(
                v for k, v in self.spark.newest.items() if self.query.endswith(f"FROM {k}")
            )
            return [{"newest": newest}]
        return [{"rows": self.spark.window_rows}]


class FakeSpark:
    """Answers the partition and count queries."""

    def __init__(
        self, points=date(2026, 10, 30), coverage=date(2026, 11, 1), window_rows=7, reports=True
    ):
        self.newest = {POINTS: points, COVERAGE: coverage}
        self.reports = reports
        self.window_rows = window_rows
        self.copied: dict[str, str] = {}
        self.settings: dict[str, str] = {}
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                if name == REPORTS:
                    return spark.reports
                return name == WINDOWS or spark.newest.get(name) is not None

        class Conf:
            def set(self, key, value):
                spark.settings[key] = value

        self.catalog, self.conf = Catalog(), Conf()

    def sql(self, query):
        return FakeFrame(self, query)


def _copy(spark, tmp_path):
    return copy_tables_for_dbt(
        spark, RUN_DATE, namespace=NAMESPACE, input_dir=tmp_path, run_time=RUN_TIME
    )


def test_each_table_is_copied_from_the_partition_the_models_use(tmp_path):
    spark = FakeSpark()
    _copy(spark, tmp_path)
    assert set(spark.copied) == {
        "trail_point",
        "trail_point_coverage",
        "satellite_window",
        "signal_report",
    }
    assert "DATE '2026-10-30'" in spark.copied["trail_point"]
    assert "DATE '2026-11-01'" in spark.copied["trail_point_coverage"]
    assert "DATE '2026-11-05'" in spark.copied["satellite_window"]


def test_times_are_written_as_utc_instants_duckdb_reads_exactly(tmp_path):
    spark = FakeSpark()
    _copy(spark, tmp_path)
    assert spark.settings["spark.sql.parquet.outputTimestampType"] == "TIMESTAMP_MICROS"


def test_the_step_reports_what_it_copied(tmp_path):
    assert _copy(FakeSpark(), tmp_path) == {
        "trail_point_date": "2026-10-30",
        "coverage_date": "2026-11-01",
        "windows": 7,
    }


def test_no_windows_for_tonight_stops_the_step(tmp_path):
    with pytest.raises(ValueError, match="no satellite windows for 2026-11-05"):
        _copy(FakeSpark(window_rows=0), tmp_path)


def test_no_trail_points_stops_the_step(tmp_path):
    with pytest.raises(ValueError, match="no trail points"):
        _copy(FakeSpark(points=None), tmp_path)


def test_coverage_older_than_the_points_stops_the_step(tmp_path):
    with pytest.raises(ValueError, match="older than the newest trail points"):
        _copy(FakeSpark(points=date(2026, 11, 2), coverage=date(2026, 11, 1)), tmp_path)


def test_no_coverage_stops_the_step(tmp_path):
    with pytest.raises(ValueError, match="no coverage flags"):
        _copy(FakeSpark(coverage=None), tmp_path)


def test_the_reports_of_the_7_days_before_the_run_are_copied_for_the_area_counts(tmp_path):
    # ADR 0030 counts the last 7 days. Times are compared as epoch seconds, because no Spark
    # session here sets a time zone. 1793872800 is 2026-11-05T10:00Z, 1793268000 is 7 days before.
    spark = FakeSpark()
    _copy(spark, tmp_path)
    query = spark.copied["signal_report"]
    assert f"FROM {REPORTS}" in query
    assert "unix_timestamp(report_hour_utc) > 1793268000" in query
    assert "unix_timestamp(report_hour_utc) <= 1793872800" in query


def test_only_the_report_fields_the_counts_need_are_copied(tmp_path):
    spark = FakeSpark()
    _copy(spark, tmp_path)
    assert spark.copied["signal_report"].startswith(
        "SELECT report_id, h3_cell_res9, carrier, had_signal, report_hour_utc FROM"
    )


def test_no_report_table_stops_the_step(tmp_path):
    with pytest.raises(ValueError, match="copy_reports runs first"):
        _copy(FakeSpark(reports=False), tmp_path)
