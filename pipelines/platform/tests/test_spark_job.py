"""Tests for the Spark sample job, using a fake Spark session.

Real Spark runs in CI (pipelines/platform/spark). These tests check the rules the job
must follow: the row limit stops the job before any write, a first run creates the
partitioned table, and a rerun only overwrites partitions.
"""

from datetime import UTC, date, datetime

import pytest
from sample_iceberg_job import CATALOG_NAME, RowLimitExceeded, run_sample_iceberg_job
from sample_rows import build_sample_rows

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
RUN_DATE = date(2026, 10, 9)
TABLE = "sample_answer"
FULL_NAME = f"{CATALOG_NAME}.{TABLE}"


class FakeWriter:
    """Records which write method the job called."""

    def __init__(self, calls: list[str]):
        self.calls = calls

    def partitionedBy(self, column: str):  # noqa: N802, Spark method name
        self.calls.append(f"partitionedBy:{column}")
        return self

    def create(self) -> None:
        self.calls.append("create")

    def overwritePartitions(self) -> None:  # noqa: N802, Spark method name
        self.calls.append("overwritePartitions")


class FakeFrame:
    """Stands in for a Spark DataFrame."""

    def __init__(self, rows: list[dict], calls: list[str]):
        self.rows = rows
        self.calls = calls

    def writeTo(self, name: str) -> FakeWriter:  # noqa: N802, Spark method name
        self.calls.append(f"writeTo:{name}")
        return FakeWriter(self.calls)

    def count(self) -> int:
        return len(self.rows)


class FakeCatalog:
    def __init__(self, existing: set[str]):
        self.existing = existing

    def tableExists(self, name: str) -> bool:  # noqa: N802, Spark method name
        return name in self.existing


class FakeSpark:
    def __init__(self, existing_tables: set[str] | None = None):
        self.calls: list[str] = []
        self.catalog = FakeCatalog(existing_tables or set())

    def createDataFrame(self, rows: list[dict]) -> FakeFrame:  # noqa: N802, Spark method name
        self.calls.append("createDataFrame")
        return FakeFrame(rows, self.calls)


def test_rows_over_the_limit_stop_the_job_before_any_write():
    spark = FakeSpark()
    with pytest.raises(RowLimitExceeded, match="over the limit of 2"):
        run_sample_iceberg_job(spark, TABLE, RUN_DATE, NOW, max_rows=2)
    assert "createDataFrame" not in spark.calls
    assert not any(call.startswith("writeTo") for call in spark.calls)


def test_first_run_creates_the_table_partitioned_by_run_date():
    spark = FakeSpark(existing_tables=set())
    written = run_sample_iceberg_job(spark, TABLE, RUN_DATE, NOW, max_rows=100)
    assert written == 3
    assert spark.calls == [
        "createDataFrame",
        f"writeTo:{FULL_NAME}",
        "partitionedBy:run_date",
        "create",
    ]


def test_rerun_overwrites_partitions_and_does_not_recreate_the_table():
    spark = FakeSpark(existing_tables={FULL_NAME})
    run_sample_iceberg_job(spark, TABLE, RUN_DATE, NOW, max_rows=100)
    assert spark.calls == [
        "createDataFrame",
        f"writeTo:{FULL_NAME}",
        "overwritePartitions",
    ]


def test_sample_rows_carry_the_run_date_and_a_utc_time():
    rows = build_sample_rows(NOW, RUN_DATE)
    assert len(rows) == 3
    assert {row["run_date"] for row in rows} == {RUN_DATE}
    assert {row["last_good_run_utc"] for row in rows} == {NOW}


def test_sample_rows_refuse_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_sample_rows(datetime(2026, 10, 9, 10, 0), RUN_DATE)
