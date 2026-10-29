"""Tests that run the Spark job and the maintenance task on real Spark and a real Iceberg table.

These need pyspark, Java and a download of the Iceberg runtime, so they skip when pyspark
is not installed. The CI job named "Spark tests" installs it and runs them on Linux.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from iceberg_maintenance import maintain_tables  # noqa: E402
from sample_iceberg_job import (  # noqa: E402
    CATALOG_NAME,
    RowLimitExceeded,
    build_spark_session,
    run_sample_iceberg_job,
)

NOW = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)
TODAY = date(2026, 10, 10)
TOMORROW = TODAY + timedelta(days=1)
NAMESPACE = "platform"


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    warehouse = tmp_path_factory.mktemp("warehouse")
    session = build_spark_session("integration_tests", str(warehouse))
    yield session
    session.stop()


def _row_count(spark, table: str) -> int:
    return spark.table(f"{CATALOG_NAME}.{NAMESPACE}.{table}").count()


def test_first_run_creates_a_table_with_the_three_sample_rows(spark):
    written = run_sample_iceberg_job(
        spark, "first_run", TODAY, NOW, namespace=NAMESPACE, max_rows=100
    )

    assert written == 3
    assert _row_count(spark, "first_run") == 3


def test_rerunning_the_same_day_keeps_the_same_rows(spark):
    run_sample_iceberg_job(spark, "rerun", TODAY, NOW, namespace=NAMESPACE, max_rows=100)
    run_sample_iceberg_job(spark, "rerun", TODAY, NOW, namespace=NAMESPACE, max_rows=100)

    assert _row_count(spark, "rerun") == 3


def test_a_new_day_adds_a_partition_and_leaves_the_old_one(spark):
    run_sample_iceberg_job(spark, "two_days", TODAY, NOW, namespace=NAMESPACE, max_rows=100)
    run_sample_iceberg_job(
        spark, "two_days", TOMORROW, NOW + timedelta(days=1), namespace=NAMESPACE, max_rows=100
    )

    assert _row_count(spark, "two_days") == 6


def test_the_row_limit_stops_the_job_before_the_table_exists(spark):
    with pytest.raises(RowLimitExceeded):
        run_sample_iceberg_job(spark, "too_big", TODAY, NOW, namespace=NAMESPACE, max_rows=2)

    assert not spark.catalog.tableExists(f"{CATALOG_NAME}.{NAMESPACE}.too_big")


def test_maintenance_runs_on_a_real_table_and_keeps_its_rows(spark):
    run_sample_iceberg_job(spark, "maintained", TODAY, NOW, namespace=NAMESPACE, max_rows=100)

    maintain_tables(spark, ["maintained"], NOW, namespace=NAMESPACE)

    assert _row_count(spark, "maintained") == 3


class AirflowTime(datetime):
    """Stands in for pendulum.DateTime, the datetime subclass a scheduled run gets from Airflow."""


def test_a_scheduled_runs_time_type_is_written_as_a_timestamp(spark):
    run_sample_iceberg_job(spark, "scheduled", TODAY, NOW, namespace=NAMESPACE, max_rows=100)
    scheduled_time = AirflowTime(2026, 10, 11, 10, 0, tzinfo=UTC)

    run_sample_iceberg_job(
        spark, "scheduled", TOMORROW, scheduled_time, namespace=NAMESPACE, max_rows=100
    )

    table = spark.table(f"{CATALOG_NAME}.{NAMESPACE}.scheduled")
    assert table.schema["last_good_run_utc"].dataType.simpleString() == "timestamp"
    assert table.where(f"run_date = '{TOMORROW}'").count() == 3
