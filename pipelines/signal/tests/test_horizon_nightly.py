"""Tests for the nightly horizon step (C4): when it recomputes, what it fetches, what it writes.

Spark, S3 and the GLO-30 archive are fakes. Each fake tile is a small flat GeoTIFF placed where
the real tile would be, so the whole path from download to written rows runs for real.
"""

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from elevation_source import MANIFEST_PREFIX, tile_name
from sample_iceberg_job import CATALOG_NAME
from signal_nightly import compute_horizons_if_needed
from terrain_horizon import SECTORS, compute_horizons
from test_geotiff import write_tiff
from test_signal_nightly import FakeResponse, FakeS3
from trail_loader import TrailPoint

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NOW = datetime(2026, 11, 3, 10, 5, tzinfo=UTC)
RUN_DATE = date(2026, 11, 3)
NAMESPACE = "portfolio_dev"
POINTS_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point"
HORIZON_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point_horizon"

POINT_ROWS = [
    {
        "trail_point_id": f"tp-{n}",
        "trail_id": "t-1",
        "trail_name": "Bright Angel Trail",
        "unit_code": "GRCA",
        "seq": n,
        "lon": -112.14 + n * 0.0005,
        "lat": 36.06,
    }
    for n in range(3)
]


class TileOpener:
    """Answers each GLO-30 URL with a flat 1000 m tile at that tile's own place."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.urls = []

    def __call__(self, url, timeout):
        self.urls.append(url)
        for lat in (35, 36):
            for lon in (-113, -112):
                if tile_name(lat, lon) in url:
                    path = self.tmp_path / f"fake_{lat}_{lon}.tif"
                    step = 1 / 120  # coarse cells keep the test fast
                    cells = 121  # pixel is point: 121 centres span the whole degree
                    heights = np.full((cells, cells), 1000.0, dtype=np.float32)
                    write_tiff(path, heights, west=lon, north=lat + 1, step_deg=step, tile=64)
                    return FakeResponse(path.read_bytes())
        raise AssertionError(f"unexpected URL {url}")


class FakeSpark:
    """Answers the newest-partition queries and the trail point read; runs partitions in order."""

    def __init__(self, points_date=None, horizon_date=None):
        self.points_date = points_date
        self.horizon_date = horizon_date
        self.written: dict[str, list[dict]] = {}
        self.partitions_asked = None
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return (name == POINTS_TABLE and spark.points_date is not None) or (
                    name == HORIZON_TABLE and spark.horizon_date is not None
                )

        class Rdd:
            def __init__(self, items):
                self.items = items

            def mapPartitions(self, fn):  # noqa: N802, Spark method name
                return Rdd(list(fn(iter(self.items))))

            def collect(self):
                return self.items

        class Context:
            def parallelize(self, items, partitions):
                spark.partitions_asked = partitions
                return Rdd(list(items))

        self.catalog = Catalog()
        self.sparkContext = Context()  # noqa: N815, Spark attribute name

    def sql(self, statement):
        if "MAX(run_date)" in statement:
            value = self.horizon_date if HORIZON_TABLE in statement else self.points_date
            rows = [{"newest": value}]
        else:
            assert POINTS_TABLE in statement and str(self.points_date) in statement
            rows = POINT_ROWS
        return type("Result", (), {"collect": lambda _self: rows})()

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        spark = self

        class Writer:
            def __init__(self, name):
                self.name = name

            def partitionedBy(self, column):  # noqa: N802, Spark method name
                return self

            def create(self):
                spark.written[self.name.rsplit(".", 1)[1]] = rows

            def overwritePartitions(self):  # noqa: N802, Spark method name
                spark.written[self.name.rsplit(".", 1)[1]] = rows

        return type("Frame", (), {"writeTo": lambda _self, name: Writer(name)})()


def run(spark: FakeSpark, s3: FakeS3, tmp_path: Path, opener=None) -> dict:
    work = tmp_path / "tiles"
    work.mkdir(exist_ok=True)
    return compute_horizons_if_needed(
        spark,
        s3,
        "raw",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        now_utc=NOW,
        work_dir=work,
        opener=opener or TileOpener(tmp_path),
    )


def test_the_first_run_computes_a_horizon_for_every_trail_point(tmp_path: Path):
    spark, s3 = FakeSpark(points_date=date(2026, 10, 30)), FakeS3()

    result = run(spark, s3, tmp_path)

    assert result == {"changed": True, "points": 3, "tiles": 4}
    rows = spark.written["trail_point_horizon"]
    assert [row["trail_point_id"] for row in rows] == ["tp-0", "tp-1", "tp-2"]
    assert all(row["horizon_angles_deg"] == [0.0] * SECTORS for row in rows)  # flat fake tiles
    assert {row["run_date"] for row in rows} == {RUN_DATE}
    assert {row["computed_at_utc"] for row in rows} == {NOW}


def test_each_row_names_the_manifest_of_the_tiles_it_came_from(tmp_path: Path):
    spark, s3 = FakeSpark(points_date=date(2026, 10, 30)), FakeS3()

    run(spark, s3, tmp_path)

    (key,) = [k for k in s3.objects if k.startswith(MANIFEST_PREFIX)]

    expected = hashlib.sha256(s3.objects[key]).hexdigest()
    rows = spark.written["trail_point_horizon"]
    assert {row["elevation_source_manifest_sha256"] for row in rows} == {expected}


def test_horizons_newer_than_the_trail_points_are_not_computed_again(tmp_path: Path):
    spark = FakeSpark(points_date=date(2026, 10, 30), horizon_date=date(2026, 10, 31))
    opener = TileOpener(tmp_path)

    assert run(spark, FakeS3(), tmp_path, opener) == {"changed": False}
    assert opener.urls == []
    assert spark.written == {}


def test_new_trail_points_are_given_new_horizons(tmp_path: Path):
    spark = FakeSpark(points_date=date(2026, 11, 3), horizon_date=date(2026, 10, 31))

    assert run(spark, FakeS3(), tmp_path)["changed"] is True


def test_no_trail_points_yet_is_an_error(tmp_path: Path):
    with pytest.raises(ValueError, match="no trail points"):
        run(FakeSpark(), FakeS3(), tmp_path)


def test_compute_horizons_spreads_points_over_spark_partitions(tmp_path: Path):
    spark = FakeSpark()
    path = tmp_path / "flat.tif"
    heights = np.full((121, 121), 500.0, dtype=np.float32)
    write_tiff(path, heights, west=-113.0, north=37.0, step_deg=1 / 120, tile=64)
    points = [TrailPoint(f"tp-{n}", "t", "T", "GRCA", n, -112.5, 36.5) for n in range(2)]

    horizons = compute_horizons(spark, points, [path], partitions=4)

    assert spark.partitions_asked == 4
    assert [h.trail_point_id for h in horizons] == ["tp-0", "tp-1"]
