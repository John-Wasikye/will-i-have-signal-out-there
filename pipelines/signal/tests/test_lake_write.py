"""Tests for the lake writer: column types come from the table's contract, never from a guess.

Spark guesses a column's type from the Python values when it is not told. That failed the live
skeleton run on 2026-10-29 (INC-2026-10-29-01), and it cannot guess at all for a column that is
None in every row. These tests use a fake Spark; test_lake_write_spark.py uses the real one.
"""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from lake_write import (
    Column,
    conform_rows,
    contract_columns,
    spark_schema,
    write_run_partition,
)

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
RUN_DATE = date(2026, 10, 28)
COLUMNS = (
    Column("trail_line_id", "string", required=True),
    Column("trlname", "string", required=False),
    Column("seq", "integer", required=True),
    Column("lon", "number", required=True),
    Column("fetched_at_utc", "timestamp", required=True),
)


class AirflowTime(datetime):
    """Stands in for pendulum.DateTime, the datetime subclass a scheduled run gets from Airflow."""


class AirflowDate(date):
    """Stands in for pendulum.Date, which a scheduled run's time gives for ``.date()``."""


def _row(**changes) -> dict:
    row = {
        "trail_line_id": "1",
        "trlname": "Bright Angel Trail",
        "seq": 0,
        "lon": -112.14,
        "fetched_at_utc": datetime(2026, 10, 28, 4, 30, tzinfo=UTC),
    }
    return row | changes


def test_contract_columns_are_read_in_order_with_their_types():
    columns = contract_columns(CONTRACTS / "nps_trails.yaml", "nps_trail_line")
    assert [column.name for column in columns] == [
        "trail_line_id",
        "trlname",
        "unitcode",
        "geometry_geojson",
        "source_url",
        "fetched_at_utc",
        "content_sha256",
    ]
    assert columns[1] == Column("trlname", "string", required=False)
    assert columns[5] == Column("fetched_at_utc", "timestamp", required=True)


def test_contract_columns_refuse_a_table_the_contract_does_not_define():
    with pytest.raises(ValueError, match="no table named trail_point"):
        contract_columns(CONTRACTS / "nps_trails.yaml", "trail_point")


def test_the_schema_declares_every_column_and_the_run_date():
    assert spark_schema(COLUMNS) == (
        "trail_line_id STRING NOT NULL, trlname STRING, seq BIGINT NOT NULL, "
        "lon DOUBLE NOT NULL, fetched_at_utc TIMESTAMP NOT NULL, run_date DATE NOT NULL"
    )


def test_the_schema_refuses_a_type_it_does_not_know():
    with pytest.raises(ValueError, match="geometry: no Spark type for logical type 'object'"):
        spark_schema((Column("geometry", "object", required=True),))


def test_a_whole_number_in_a_number_column_becomes_a_float():
    rows = conform_rows([_row(lon=0)], COLUMNS, RUN_DATE)
    assert type(rows[0]["lon"]) is float


def test_every_row_gets_the_run_date():
    rows = conform_rows([_row(), _row(seq=1)], COLUMNS, RUN_DATE)
    assert [row["run_date"] for row in rows] == [RUN_DATE, RUN_DATE]


def test_a_missing_column_is_refused_by_name():
    row = _row()
    del row["seq"]
    with pytest.raises(ValueError, match="missing seq"):
        conform_rows([row], COLUMNS, RUN_DATE)


def test_a_column_the_contract_does_not_have_is_refused_by_name():
    with pytest.raises(ValueError, match="unexpected elevation_m"):
        conform_rows([_row(elevation_m=812.0)], COLUMNS, RUN_DATE)


def test_an_empty_required_column_is_refused():
    with pytest.raises(ValueError, match="trail_line_id is required"):
        conform_rows([_row(trail_line_id=None)], COLUMNS, RUN_DATE)


def test_an_empty_optional_column_is_kept_empty():
    rows = conform_rows([_row(trlname=None)], COLUMNS, RUN_DATE)
    assert rows[0]["trlname"] is None


def test_an_airflow_time_and_date_come_back_as_plain_utc_types():
    eastern = timezone(timedelta(hours=-4))
    rows = conform_rows(
        [_row(fetched_at_utc=AirflowTime(2026, 10, 28, 0, 30, tzinfo=eastern))],
        COLUMNS,
        AirflowDate(2026, 10, 28),
    )
    assert type(rows[0]["fetched_at_utc"]) is datetime
    assert rows[0]["fetched_at_utc"] == datetime(2026, 10, 28, 4, 30, tzinfo=UTC)
    assert type(rows[0]["run_date"]) is date


def test_a_naive_time_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        conform_rows([_row(fetched_at_utc=datetime(2026, 10, 28, 4, 30))], COLUMNS, RUN_DATE)


class FakeSpark:
    def __init__(self, table_exists: bool):
        self.calls = []
        exists = table_exists

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return exists

        self.catalog = Catalog()

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        self.rows = rows
        self.schema = schema
        spark = self

        class Writer:
            def partitionedBy(self, column):  # noqa: N802, Spark method name
                spark.calls.append(f"partitionedBy:{column}")
                return self

            def create(self):
                spark.calls.append("create")

            def overwritePartitions(self):  # noqa: N802, Spark method name
                spark.calls.append("overwritePartitions")

        class Frame:
            def writeTo(self, name):  # noqa: N802, Spark method name
                spark.calls.append(f"writeTo:{name}")
                return Writer()

        return Frame()


def test_the_write_hands_spark_the_declared_schema_and_the_conformed_rows():
    spark = FakeSpark(table_exists=False)
    written = write_run_partition(
        spark, "nps_trail_line", [_row(lon=0)], RUN_DATE, columns=COLUMNS, namespace="p"
    )
    assert written == 1
    assert spark.schema == spark_schema(COLUMNS)
    assert spark.rows == conform_rows([_row(lon=0)], COLUMNS, RUN_DATE)
    assert spark.calls == ["writeTo:portfolio.p.nps_trail_line", "partitionedBy:run_date", "create"]


def test_a_rerun_overwrites_only_its_partition():
    spark = FakeSpark(table_exists=True)
    write_run_partition(spark, "t", [_row()], RUN_DATE, columns=COLUMNS, namespace="p")
    assert spark.calls == ["writeTo:portfolio.p.t", "overwritePartitions"]


def test_the_write_refuses_no_rows():
    with pytest.raises(ValueError, match="no rows"):
        write_run_partition(FakeSpark(False), "t", [], RUN_DATE, columns=COLUMNS, namespace="p")
