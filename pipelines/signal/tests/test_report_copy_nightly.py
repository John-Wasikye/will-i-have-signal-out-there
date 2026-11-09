"""Tests for the nightly report copy step (C23) as the DAG runs it.

A small fake Spark keeps each table's rows, so the step's writes, deletes and recount can be
followed. The DynamoDB fake comes from test_report_copy.py. No test calls AWS.
"""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import h3
import pytest
from report_copy import CONTRADICTING_BURST, OUTSIDE_MAPPED_AREA
from sample_iceberg_job import CATALOG_NAME
from signal_nightly import copy_reports
from test_report_copy import FAR, NEAR, FakeDynamoDB, _item

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NAMESPACE = "portfolio_dev"
RUN_DATE = date(2026, 11, 10)
RUN_TIME = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
POINTS = f"{CATALOG_NAME}.{NAMESPACE}.trail_point"
REPORTS = f"{CATALOG_NAME}.{NAMESPACE}.signal_report"
SET_ASIDE = f"{CATALOG_NAME}.{NAMESPACE}.signal_report_set_aside"
CELL_DAY = f"{CATALOG_NAME}.{NAMESPACE}.report_cell_day"
POINT_ROWS = [
    {
        "trail_point_id": "grca-bright-angel-00000",
        "trail_id": "grca-bright-angel",
        "trail_name": "Bright Angel Trail",
        "unit_code": "GRCA",
        "seq": 0,
        "lon": -112.143,
        "lat": 36.0579,
        "run_date": date(2026, 10, 30),
    }
]


class FakeSpark:
    """Keeps rows per table and answers the few queries the step makes."""

    def __init__(self, tables: dict[str, list[dict]] | None = None) -> None:
        self.tables = {name: list(rows) for name, rows in (tables or {}).items()}
        self.statements: list[str] = []
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return name in spark.tables

        self.catalog = Catalog()

    def sql(self, statement: str):
        self.statements.append(statement)
        rows = self._answer(statement)

        class Result:
            def collect(self):
                return rows

        return Result()

    def _answer(self, statement: str) -> list[dict]:
        if statement.startswith("DELETE"):
            return []
        if "MAX(run_date)" in statement:
            return [{"newest": max(row["run_date"] for row in self.tables[POINTS])}]
        if f"FROM {POINTS}" in statement:
            return self.tables[POINTS]
        if f"FROM {REPORTS}" in statement:
            first = int(re.search(r"timestamp_seconds\((\d+)\)", statement).group(1))
            return [
                {
                    "h3_cell_res9": row["h3_cell_res9"],
                    "had_signal": row["had_signal"],
                    "hour_epoch": int(row["report_hour_utc"].timestamp()),
                }
                for row in self.tables[REPORTS]
                if row["report_hour_utc"].timestamp() >= first
            ]
        raise AssertionError(f"unexpected query: {statement}")

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        spark = self

        class Writer:
            def __init__(self, name):
                self.name = name

            def partitionedBy(self, column):  # noqa: N802, Spark method name
                return self

            def create(self):
                spark.tables[self.name] = list(rows)

            def append(self):
                spark.tables[self.name].extend(rows)

            def overwritePartitions(self):  # noqa: N802, Spark method name
                nights = {row["run_date"] for row in rows}
                kept = [row for row in spark.tables[self.name] if row["run_date"] not in nights]
                spark.tables[self.name] = kept + list(rows)

        class Frame:
            def writeTo(self, name):  # noqa: N802, Spark method name
                return Writer(name)

        return Frame()


def _copy(spark, dynamodb):
    return copy_reports(
        spark,
        dynamodb,
        "portfolio-dev-signal-reports",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        run_time=RUN_TIME,
    )


def _burst_items() -> list[dict]:
    hour = {"report_hour_utc": {"S": "2026-11-09T15:00:00Z"}}
    return [
        _item("burst-1", **hour),
        _item("burst-2", **hour),
        _item("burst-3", had_signal={"BOOL": False}, **hour),
    ]


def test_a_night_copies_kept_reports_sets_aside_the_rest_and_marks_every_one():
    spark = FakeSpark({POINTS: POINT_ROWS})
    dynamodb = FakeDynamoDB(
        [
            [
                _item("a"),
                _item("b", had_signal={"BOOL": False}),
                _item("far", h3_cell_res9={"S": FAR}),
            ]
        ]
        + [_burst_items()]
    )

    summary = _copy(spark, dynamodb)

    assert summary == {"copied": 6, "set_aside": 4, "marked": 6, "cell_days": 1}
    assert sorted(row["report_id"] for row in spark.tables[REPORTS]) == ["a", "b"]
    assert {row["run_date"] for row in spark.tables[REPORTS]} == {RUN_DATE}
    assert {row["copied_at_utc"] for row in spark.tables[REPORTS]} == {RUN_TIME}
    reasons = {row["report_id"]: row["reason"] for row in spark.tables[SET_ASIDE]}
    assert reasons == {
        "far": OUTSIDE_MAPPED_AREA,
        "burst-1": CONTRADICTING_BURST,
        "burst-2": CONTRADICTING_BURST,
        "burst-3": CONTRADICTING_BURST,
    }
    marked = [update["Key"]["report_id"]["S"] for update in dynamodb.updates]
    assert sorted(marked) == ["a", "b", "burst-1", "burst-2", "burst-3", "far"]
    expires = int((RUN_TIME + timedelta(days=30)).timestamp())
    assert {u["ExpressionAttributeValues"][":expires"]["N"] for u in dynamodb.updates} == {
        str(expires)
    }


def test_the_daily_counts_hold_only_the_kept_reports():
    spark = FakeSpark({POINTS: POINT_ROWS})
    dynamodb = FakeDynamoDB([[_item("a"), _item("b", had_signal={"BOOL": False})], _burst_items()])

    _copy(spark, dynamodb)

    [row] = spark.tables[CELL_DAY]
    assert row["h3_cell_res9"] == NEAR
    assert row["report_date_utc"] == date(2026, 11, 9)
    assert (row["report_count"], row["signal_yes_count"], row["signal_no_count"]) == (2, 1, 1)
    assert row["built_at_utc"] == RUN_TIME


def test_counts_of_recent_days_are_recounted_and_older_days_are_kept():
    old_count = {
        "h3_cell_res9": NEAR,
        "report_date_utc": date(2026, 10, 1),
        "report_count": 4,
        "signal_yes_count": 4,
        "signal_no_count": 0,
        "built_at_utc": datetime(2026, 10, 2, 10, tzinfo=UTC),
        "run_date": date(2026, 10, 2),
    }
    spark = FakeSpark({POINTS: POINT_ROWS, CELL_DAY: [old_count]})

    _copy(spark, FakeDynamoDB([[_item("a")]]))

    assert f"DELETE FROM {CELL_DAY} WHERE report_date_utc >= DATE '2026-10-21'" in spark.statements
    assert old_count in spark.tables[CELL_DAY]


def test_a_rerun_of_the_night_rewrites_the_same_copy():
    spark = FakeSpark({POINTS: POINT_ROWS})
    items = [[_item("a"), _item("b")]]

    _copy(spark, FakeDynamoDB(items))
    _copy(spark, FakeDynamoDB(items))

    assert sorted(row["report_id"] for row in spark.tables[REPORTS]) == ["a", "b"]


def test_partitions_more_than_30_days_old_are_deleted_from_both_report_tables():
    spark = FakeSpark({POINTS: POINT_ROWS})

    _copy(spark, FakeDynamoDB([[_item("a"), _item("far", h3_cell_res9={"S": FAR})]]))

    for table in (REPORTS, SET_ASIDE):
        assert f"DELETE FROM {table} WHERE run_date < DATE '2026-10-11'" in spark.statements


def test_reports_are_marked_only_after_the_lake_write_succeeds():
    class FailingWrite(FakeSpark):
        def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
            raise RuntimeError("the lake write failed")

    dynamodb = FakeDynamoDB([[_item("a")]])

    with pytest.raises(RuntimeError, match="lake write"):
        _copy(FailingWrite({POINTS: POINT_ROWS}), dynamodb)

    assert dynamodb.updates == []


def test_the_copy_stops_without_trail_points_and_marks_nothing():
    dynamodb = FakeDynamoDB([[_item("a")]])

    with pytest.raises(ValueError, match="trail_point"):
        _copy(FakeSpark(), dynamodb)

    assert dynamodb.updates == []


def test_a_night_with_no_reports_marks_nothing_and_counts_nothing():
    spark = FakeSpark({POINTS: POINT_ROWS})
    dynamodb = FakeDynamoDB([[]])

    summary = _copy(spark, dynamodb)

    assert summary == {"copied": 0, "set_aside": 0, "marked": 0, "cell_days": 0}
    assert dynamodb.updates == []
    assert spark.tables[REPORTS] == []


def test_the_cell_in_a_copied_row_is_still_a_resolution_9_cell():
    spark = FakeSpark({POINTS: POINT_ROWS})

    _copy(spark, FakeDynamoDB([[_item("a")]]))

    assert h3.get_resolution(spark.tables[REPORTS][0]["h3_cell_res9"]) == 9
