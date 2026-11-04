"""run_window_job on real Spark, in local mode as on the session box.

The fake Spark in test_window_job.py runs each partition in this process. Real Spark sends the
work to separate Python worker processes, which must import the window code and sgp4 and read
the broadcast positions, and it checks each row against the contract's schema. This test checks
that part. It skips where pyspark is not installed; CI's "Spark tests" job runs it.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

from satellite_windows import WINDOW_COLUMNS, run_window_job  # noqa: E402
from test_window_job import COLUMNS, HORIZONS, POINTS, RUN, SATELLITES, expected_windows  # noqa: E402

SIGNAL = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    # As in test_terrain_horizon_spark.py: the workers import by name from the PYTHONPATH the
    # first Spark session started with, which CI's Spark step sets as the image does.
    entries = os.environ.get("PYTHONPATH", "").split(os.pathsep)
    search_path = [Path(entry).resolve() for entry in entries if entry]
    assert SIGNAL.resolve() in search_path, f"PYTHONPATH must include {SIGNAL}, as the image's does"
    session = SparkSession.builder.master("local[2]").appName("window_tests").getOrCreate()
    yield session
    session.stop()


def test_real_spark_finds_the_same_windows_with_the_contract_types(spark):
    frame = run_window_job(spark, RUN, SATELLITES, POINTS, HORIZONS, COLUMNS, partitions=2)

    assert tuple(frame.columns) == WINDOW_COLUMNS
    types = dict(frame.dtypes)
    assert types["window_start_utc"] == "timestamp"
    assert types["min_elevation_deg"] == "double"
    assert types["run_date"] == "date"
    rows = frame.collect()
    found = sorted(
        (r["trail_point_id"], r["satellite_id"], r["window_start_utc"], r["window_end_utc"])
        for r in rows
    )
    # Spark hands timestamps back as naive local times, so compare as UTC instants.
    expected = [(p, s, a.timestamp(), b.timestamp()) for p, s, a, b in expected_windows()]
    assert [(p, s, a.timestamp(), b.timestamp()) for p, s, a, b in found] == expected
    assert frame.count() == len(expected) > 0
