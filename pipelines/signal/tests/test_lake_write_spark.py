"""The lake writer's schema and rows on real Spark, without Iceberg.

Building the DataFrame is where Spark guesses or checks types, so no table is needed. These tests
skip where pyspark is not installed; CI's "Spark tests" job runs them.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from lake_write import conform_rows, contract_columns, spark_schema  # noqa: E402

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
RUN_DATE = date(2026, 10, 28)
FETCHED_AT = datetime(2026, 10, 28, 4, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = SparkSession.builder.master("local[1]").appName("lake_write_tests").getOrCreate()
    yield session
    session.stop()


def _frame(spark, rows, columns):
    return spark.createDataFrame(
        conform_rows(rows, columns, RUN_DATE), schema=spark_schema(columns)
    )


def test_a_column_that_is_empty_in_every_row_still_gets_its_type(spark):
    columns = contract_columns(CONTRACTS / "nps_trails.yaml", "nps_trail_line")
    row = {
        "trail_line_id": "1",
        "trlname": None,
        "unitcode": "GRCA",
        "geometry_geojson": "{}",
        "source_url": "u",
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": "h",
    }

    frame = _frame(spark, [row], columns)

    assert frame.schema["trlname"].dataType.simpleString() == "string"
    assert frame.schema["fetched_at_utc"].dataType.simpleString() == "timestamp"
    assert frame.schema["run_date"].dataType.simpleString() == "date"


def test_a_whole_number_in_a_number_column_is_stored_as_a_double(spark):
    columns = contract_columns(CONTRACTS / "celestrak_gp.yaml", "celestrak_gp")
    row = {column.name: 1.5 for column in columns} | {
        "norad_cat_id": 90001,
        "epoch_utc": FETCHED_AT,
        "object_name": "STARLINK-90001",
        "bstar": 0,
        "source_url": "u",
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": "h",
    }

    frame = _frame(spark, [row], columns)

    assert frame.schema["bstar"].dataType.simpleString() == "double"
    assert frame.schema["norad_cat_id"].dataType.simpleString() == "bigint"
    assert frame.collect()[0]["bstar"] == 0.0
