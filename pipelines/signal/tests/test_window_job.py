"""Tests for the satellite window Spark job (C5): it propagates once, checks every trail point in
parallel, and hands Spark rows in the contract's column order, so 2 million rows never pass
through Airflow's own memory.

Spark is a fake that runs each partition in this process. test_window_job_spark.py runs the same
job on real Spark in CI.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from lake_write import contract_columns
from satellite_windows import (
    MIN_ELEVATION_DEG,
    SPAN_MINUTES,
    SPARK_PARTITIONS,
    WINDOW_COLUMNS,
    SatelliteElements,
    WindowRun,
    minute_times,
    propagate_satellites,
    run_window_job,
    window_rows,
    windows_for_point,
)
from terrain_horizon import SECTORS, HorizonProfile
from trail_loader import TrailPoint

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
COLUMNS = contract_columns(CONTRACTS / "satellite_window.yaml", "satellite_window")
START = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
RUN = WindowRun(
    run_date=date(2026, 11, 4),
    span_start_utc=START,
    run_started_utc=datetime(2026, 11, 4, 10, 1, tzinfo=UTC),
    loaded_at_utc=datetime(2026, 11, 4, 10, 30, tzinfo=UTC),
    span_minutes=180,  # three hours keep the tests fast; the real run uses SPAN_MINUTES
)


def satellite(norad: int, node_deg: float, anomaly_deg: float) -> SatelliteElements:
    return SatelliteElements(
        norad_cat_id=norad,
        object_name=f"STARLINK-{norad} [DTC]",
        epoch_utc=START - timedelta(hours=6),
        inclination_deg=53.0,
        eccentricity=0.0001,
        ra_of_asc_node_deg=node_deg,
        arg_of_pericenter_deg=90.0,
        mean_anomaly_deg=anomaly_deg,
        mean_motion_rev_per_day=15.85,
        bstar=0.0001,
    )


# Spread over planes and phases, so some pass over the Grand Canyon in three hours.
SATELLITES = [satellite(60000 + i, 30.0 * i, 45.0 * i) for i in range(12)]
POINTS = [
    TrailPoint(f"grca-test-{n:05d}", "grca-test", "Test", "GRCA", n, -112.1 + n * 0.01, 36.1)
    for n in range(5)
]
HORIZONS = {p.trail_point_id: HorizonProfile(p.trail_point_id, (5.0,) * SECTORS) for p in POINTS}


class FakeSpark:
    """Runs each partition in this process and keeps what the job hands to createDataFrame."""

    def __init__(self):
        self.partitions_asked = None
        self.frames = []
        spark = self

        class Rdd:
            def __init__(self, chunks):
                self.chunks = chunks

            def mapPartitions(self, fn):  # noqa: N802, Spark method name
                return Rdd([list(fn(iter(chunk))) for chunk in self.chunks])

            def rows(self):
                return [row for chunk in self.chunks for row in chunk]

        class Broadcast:
            def __init__(self, value):
                self.value = value

        class Context:
            def parallelize(self, items, partitions):
                spark.partitions_asked = partitions
                items = list(items)
                return Rdd([items[i::partitions] for i in range(partitions)])

            def broadcast(self, value):
                return Broadcast(value)

        self.sparkContext = Context()  # noqa: N815, Spark attribute name

    def createDataFrame(self, rdd, schema=None):  # noqa: N802, Spark method name
        frame = {"rows": rdd.rows(), "schema": schema}
        self.frames.append(frame)
        return frame


def expected_windows():
    times = minute_times(START, RUN.span_minutes)
    tracks = propagate_satellites(SATELLITES, times)
    return sorted(
        (w.trail_point_id, w.satellite_id, w.start_utc, w.end_utc)
        for p in POINTS
        for w in windows_for_point(p, tracks, HORIZONS[p.trail_point_id], times)
    )


def test_the_rows_follow_the_contract_and_end_with_the_partition_column():
    assert WINDOW_COLUMNS == (*(c.name for c in COLUMNS), "run_date")


def test_a_run_is_valid_until_the_end_of_its_span():
    assert RUN.valid_until_utc == START + timedelta(minutes=180)
    assert WindowRun(date(2026, 11, 4), START, START, START).span_minutes == SPAN_MINUTES


def test_the_job_finds_the_same_windows_as_the_engine():
    spark = FakeSpark()
    frame = run_window_job(spark, RUN, SATELLITES, POINTS, HORIZONS, COLUMNS)
    found = sorted(row[:4] for row in frame["rows"])
    assert found == expected_windows()
    assert len(found) > 0, "the test satellites should pass over the park at least once"


def test_every_row_carries_the_run_values():
    spark = FakeSpark()
    rows = run_window_job(spark, RUN, SATELLITES, POINTS, HORIZONS, COLUMNS)["rows"]
    for row in rows:
        values = dict(zip(WINDOW_COLUMNS, row, strict=True))
        assert values["min_elevation_deg"] == MIN_ELEVATION_DEG
        assert values["valid_until_utc"] == RUN.valid_until_utc
        assert values["run_started_utc"] == RUN.run_started_utc
        assert values["loaded_at_utc"] == RUN.loaded_at_utc
        assert values["run_date"] == date(2026, 11, 4)
        assert values["window_end_utc"] >= values["window_start_utc"]
        assert values["window_start_utc"].tzinfo is not None


def test_the_job_spreads_the_points_over_four_partitions():
    spark = FakeSpark()
    run_window_job(spark, RUN, SATELLITES, POINTS, HORIZONS, COLUMNS)
    assert SPARK_PARTITIONS == 4
    assert spark.partitions_asked == 4


def test_the_job_gives_spark_the_contract_schema():
    spark = FakeSpark()
    frame = run_window_job(spark, RUN, SATELLITES, POINTS, HORIZONS, COLUMNS)
    assert frame["schema"].startswith(
        "trail_point_id STRING NOT NULL, satellite_id STRING NOT NULL"
    )
    assert frame["schema"].endswith("run_date DATE NOT NULL")


def test_a_point_without_a_horizon_stops_the_job():
    horizons = dict(HORIZONS)
    del horizons["grca-test-00003"]
    with pytest.raises(ValueError, match="grca-test-00003"):
        run_window_job(FakeSpark(), RUN, SATELLITES, POINTS, horizons, COLUMNS)


def test_no_satellites_stops_the_job():
    with pytest.raises(ValueError, match="no satellites"):
        run_window_job(FakeSpark(), RUN, [], POINTS, HORIZONS, COLUMNS)


def test_window_rows_turns_one_chunk_of_points_into_rows():
    times = minute_times(START, RUN.span_minutes)
    tracks = propagate_satellites(SATELLITES, times)
    ids = [t.satellite_id for t in tracks]
    ecef = np.stack([t.ecef_km for t in tracks])
    items = [(p, HORIZONS[p.trail_point_id]) for p in POINTS]
    rows = list(window_rows(RUN, iter(items), ids, ecef))
    assert sorted(row[:4] for row in rows) == expected_windows()
