"""The copy for dbt on real Spark, in local mode as on the session box.

Real Spark decides how a time is stored in Parquet, which the fake in test_dbt_copy.py cannot
show. A time must arrive as the same UTC instant, or every window on the page would shift. It
skips where pyspark is not installed; CI's "Spark tests" job runs it.
"""

from datetime import UTC, date, datetime, timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from sample_iceberg_job import CATALOG_NAME  # noqa: E402
from signal_nightly import copy_tables_for_dbt  # noqa: E402

RUN_DATE = date(2026, 11, 5)
START = datetime(2026, 11, 5, 10, 5, tzinfo=UTC)
RUN_TIME = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
REPORT_SCHEMA = (
    "report_id string, h3_cell_res9 string, carrier string, had_signal boolean, "
    "report_hour_utc timestamp"
)


class CatalogView:
    """Real Spark, with the lake's table names pointing at plain temporary views."""

    def __init__(self, spark):
        self.spark, self.conf = spark, spark.conf

        class Catalog:
            def tableExists(self, _name):  # noqa: N802, Spark method name
                return True

        self.catalog = Catalog()

    def sql(self, query):
        return self.spark.sql(query.replace(f"{CATALOG_NAME}.lake.", ""))


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[1]")
        .appName("dbt_copy_tests")
        .config("spark.sql.session.timeZone", "America/Phoenix")
        .getOrCreate()
    )
    yield session
    session.stop()


def _lake_views(spark, reports):
    spark.sql(
        f"SELECT DATE '{RUN_DATE}' AS run_date, 'p' AS trail_point_id"
    ).createOrReplaceTempView("trail_point")
    spark.sql(f"SELECT DATE '{RUN_DATE}' AS run_date").createOrReplaceTempView(
        "trail_point_coverage"
    )
    spark.createDataFrame(
        [(START, RUN_DATE)], "window_start_utc timestamp, run_date date"
    ).createOrReplaceTempView("satellite_window")
    spark.createDataFrame(reports, REPORT_SCHEMA).createOrReplaceTempView("signal_report")


def _copy(spark, tmp_path):
    copy_tables_for_dbt(
        CatalogView(spark), RUN_DATE, namespace="lake", input_dir=tmp_path, run_time=RUN_TIME
    )


def test_a_copied_window_keeps_its_utc_instant(spark, tmp_path):
    _lake_views(spark, [])
    _copy(spark, tmp_path)

    (part,) = (tmp_path / "satellite_window").glob("*.parquet")
    table = pq.read_table(part)
    assert table.schema.field("window_start_utc").type == pa.timestamp("us", tz="UTC")
    assert table.to_pylist()[0]["window_start_utc"] == START


def test_a_copied_report_keeps_its_utc_hour_and_only_the_last_7_days_are_copied(spark, tmp_path):
    inside = RUN_TIME - timedelta(hours=1)
    reports = [
        ("in", "892994c5133ffff", "T-Mobile", True, inside),
        ("old", "892994c5133ffff", "T-Mobile", True, RUN_TIME - timedelta(days=7)),
        ("later", "892994c5133ffff", "T-Mobile", True, RUN_TIME + timedelta(hours=1)),
    ]
    _lake_views(spark, reports)
    _copy(spark, tmp_path)

    (part,) = (tmp_path / "signal_report").glob("*.parquet")
    table = pq.read_table(part)
    assert table.schema.field("report_hour_utc").type == pa.timestamp("us", tz="UTC")
    assert [(row["report_id"], row["report_hour_utc"]) for row in table.to_pylist()] == [
        ("in", inside)
    ]


def test_a_week_with_no_reports_still_writes_a_file_dbt_can_read(spark, tmp_path):
    _lake_views(spark, [])
    _copy(spark, tmp_path)

    parts = list((tmp_path / "signal_report").glob("*.parquet"))
    assert parts
    assert "report_hour_utc" in pq.read_schema(parts[0]).names
