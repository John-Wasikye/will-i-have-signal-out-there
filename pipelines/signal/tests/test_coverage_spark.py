"""The FCC cell file on real Spark, in local mode as on the session box.

The fake Spark in test_coverage_nightly.py reads the Parquet file with pyarrow. Real Spark checks
the file's types against the contract's schema, which is the part this test covers. It skips where
pyspark is not installed; CI's "Spark tests" job runs it.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from fcc_coverage import CellSource, FccCell, write_cells_parquet  # noqa: E402
from lake_write import contract_columns, spark_schema  # noqa: E402

CONTRACT = Path(__file__).parents[3] / "docs/trip-planner/contracts/fcc_mobile_coverage.yaml"
SOURCE = CellSource(
    release="D25_19oct2026",
    source_url="https://example.test/fcc",
    fetched_at_utc=datetime(2026, 10, 28, 3, 9, 24, tzinfo=UTC),
    content_sha256="a" * 64,
    run_date=date(2026, 11, 5),
)


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    session = SparkSession.builder.master("local[1]").appName("coverage_tests").getOrCreate()
    yield session
    session.stop()


def test_real_spark_reads_the_cell_file_with_the_contract_types(spark, tmp_path):
    path = tmp_path / "cells.parquet"
    write_cells_parquet([FccCell("89269b4001bffff", "T-Mobile", "400", 0, -110)], path, SOURCE)

    schema = spark_schema(contract_columns(CONTRACT, "fcc_coverage_cell"))
    frame = spark.read.schema(schema).parquet(path.as_uri())

    types = dict(frame.dtypes)
    assert types["environment"] == "bigint"
    assert types["min_signal_dbm"] == "bigint"
    assert types["fetched_at_utc"] == "timestamp"
    assert types["run_date"] == "date"
    row = frame.collect()[0]
    assert row["h3_cell_res9"] == "89269b4001bffff"
    assert row["min_signal_dbm"] == -110
    assert row["run_date"] == SOURCE.run_date
