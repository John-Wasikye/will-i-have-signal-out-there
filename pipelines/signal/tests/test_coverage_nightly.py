"""Tests for the nightly coverage step (C6): load the kept FCC file and flag the trail points.

The FCC site refuses automated requests, so the raw file is put in the raw bucket by hand and the
step reads the newest one. It runs only when that file or the trail points changed (ADR 0028).
No test calls AWS. The file is a tiny real GeoPackage in a real zip.
"""

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from fcc_coverage import (
    PHASE_A_PROVIDER_ID,
    WrongFccFile,
    coverage_prefix,
    point_to_cell,
    release_of,
)
from sample_iceberg_job import CATALOG_NAME
from signal_nightly import load_coverage_if_changed
from test_fcc_coverage import _gpkg
from test_signal_nightly import FakeS3

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NOW = datetime(2026, 11, 5, 10, 5, tzinfo=UTC)
RUN_DATE = date(2026, 11, 5)
NAMESPACE = "portfolio_dev"
POINTS_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point"
CELL_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.fcc_coverage_cell"
COVERAGE_TABLE = f"{CATALOG_NAME}.{NAMESPACE}.trail_point_coverage"
ZIP_NAME = "bdc_04_130403_4GLTE_mobile_broadband_h3_D25_19oct2026.zip"

POINT_ROWS = [
    {
        "trail_point_id": f"tp-{n}",
        "trail_id": "t-1",
        "trail_name": "Bright Angel Trail",
        "unit_code": "GRCA",
        "seq": n,
        "lon": -112.14,
        "lat": 36.06 + n * 0.1,
    }
    for n in range(2)
]
LISTED_CELL = point_to_cell(36.06, -112.14)


class FakeSpark:
    """Answers the partition queries, and keeps what each table was given."""

    def __init__(self, points_date=date(2026, 10, 30), coverage_date=None, loaded_hashes=()):
        self.points_date = points_date
        self.coverage_date = coverage_date
        self.loaded_hashes = list(loaded_hashes)
        self.written: dict[str, list[dict]] = {}
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return {
                    POINTS_TABLE: spark.points_date,
                    COVERAGE_TABLE: spark.coverage_date,
                    CELL_TABLE: spark.loaded_hashes or None,
                }.get(name) is not None

        class Reader:
            def schema(self, declared):
                spark.read_schema = declared
                return self

            def parquet(self, uri):
                return spark._frame(pq.read_table(uri).to_pylist())

        self.catalog = Catalog()
        self.read = Reader()

    def sql(self, statement):
        if "MAX(run_date)" in statement and "content_sha256" not in statement:
            value = self.coverage_date if COVERAGE_TABLE in statement else self.points_date
            rows = [{"newest": value}]
        elif "content_sha256" in statement:
            rows = [{"content_sha256": value} for value in self.loaded_hashes]
        else:
            rows = POINT_ROWS
        return type("Result", (), {"collect": lambda _self: rows})()

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        return self._frame(rows)

    def _frame(self, rows):
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


def _kept_file(s3, tmp_path, *, stated_hash=None):
    """Keep a zipped GeoPackage and its manifest in the fake raw bucket; return the file's hash."""
    gpkg = _gpkg(
        tmp_path / "source.gpkg",
        [
            (PHASE_A_PROVIDER_ID, "T-Mobile", 400, -110, 0, LISTED_CELL),
            (PHASE_A_PROVIDER_ID, "T-Mobile", 400, -80, 1, "89269b4004bffff"),
        ],
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(gpkg, "cells.gpkg")
    body = buffer.getvalue()
    sha256 = hashlib.sha256(body).hexdigest()
    folder = f"{coverage_prefix()}fetched_at=2026-10-28T03:09:24Z"
    s3.objects[f"{folder}/{ZIP_NAME}"] = body
    s3.objects[f"{folder}/manifest.json"] = json.dumps(
        {
            "source_url": "https://broadbandmap.fcc.gov/data-download/nationwide-data",
            "fetched_at_utc": "2026-10-28T03:09:24Z",
            "content_sha256": stated_hash or sha256,
            "size_bytes": len(body),
            "raw_key": f"{folder}/{ZIP_NAME}",
        }
    ).encode()
    return sha256


def run(spark, s3, tmp_path):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return load_coverage_if_changed(
        spark,
        s3,
        "raw",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        now_utc=NOW,
        work_dir=work,
    )


def test_the_first_run_loads_every_cell_and_flags_every_point(tmp_path):
    spark, s3 = FakeSpark(), FakeS3()
    _kept_file(s3, tmp_path)

    result = run(spark, s3, tmp_path)

    assert result == {"changed": True, "cells": 2, "points": 2, "covered": 1}
    assert [row["trail_point_id"] for row in spark.written["trail_point_coverage"]] == [
        "tp-0",
        "tp-1",
    ]
    assert [row["covered"] for row in spark.written["trail_point_coverage"]] == [True, False]


def test_each_cell_row_keeps_the_values_the_contract_lists(tmp_path):
    spark, s3 = FakeSpark(), FakeS3()
    sha256 = _kept_file(s3, tmp_path)

    run(spark, s3, tmp_path)

    first = spark.written["fcc_coverage_cell"][0]
    assert first["h3_cell_res9"] == LISTED_CELL
    assert first["carrier"] == "T-Mobile"
    assert first["technology"] == "400"
    assert first["release"] == "D25_19oct2026"
    assert first["environment"] == 0
    assert first["min_signal_dbm"] == -110
    assert first["content_sha256"] == sha256
    assert first["fetched_at_utc"] == datetime(2026, 10, 28, 3, 9, 24, tzinfo=UTC)
    assert first["run_date"] == RUN_DATE


def test_each_flag_names_the_file_it_came_from(tmp_path):
    spark, s3 = FakeSpark(), FakeS3()
    sha256 = _kept_file(s3, tmp_path)

    run(spark, s3, tmp_path)

    row = spark.written["trail_point_coverage"][0]
    assert row["carrier"] == "T-Mobile"
    assert row["technology"] == "400"
    assert row["release"] == "D25_19oct2026"
    assert row["content_sha256"] == sha256
    assert row["h3_cell_res9"] == LISTED_CELL
    assert row["run_date"] == RUN_DATE


def test_nothing_runs_when_the_file_and_the_points_are_unchanged(tmp_path):
    s3 = FakeS3()
    sha256 = _kept_file(s3, tmp_path)
    spark = FakeSpark(coverage_date=date(2026, 11, 4), loaded_hashes=[sha256])

    assert run(spark, s3, tmp_path) == {"changed": False}
    assert spark.written == {}


def test_a_new_fcc_file_loads_again(tmp_path):
    s3 = FakeS3()
    _kept_file(s3, tmp_path)
    spark = FakeSpark(coverage_date=date(2026, 11, 4), loaded_hashes=["an-older-file"])

    assert run(spark, s3, tmp_path)["changed"] is True


def test_new_trail_points_are_flagged_again(tmp_path):
    s3 = FakeS3()
    sha256 = _kept_file(s3, tmp_path)
    spark = FakeSpark(
        points_date=date(2026, 11, 5), coverage_date=date(2026, 11, 4), loaded_hashes=[sha256]
    )

    assert run(spark, s3, tmp_path)["changed"] is True


def test_stops_when_no_fcc_file_is_kept(tmp_path):
    with pytest.raises(ValueError, match="no FCC file"):
        run(FakeSpark(), FakeS3(), tmp_path)


def test_stops_when_no_trail_points_are_loaded(tmp_path):
    s3 = FakeS3()
    _kept_file(s3, tmp_path)
    with pytest.raises(ValueError, match="no trail points"):
        run(FakeSpark(points_date=None), s3, tmp_path)


def test_stops_when_the_kept_file_differs_from_its_manifest(tmp_path):
    s3 = FakeS3()
    _kept_file(s3, tmp_path, stated_hash="0" * 64)
    with pytest.raises(WrongFccFile, match="hash"):
        run(FakeSpark(), s3, tmp_path)


def test_release_comes_from_the_file_name():
    assert release_of(f"signal/fcc/x/{ZIP_NAME}") == "D25_19oct2026"


def test_a_file_name_with_no_release_is_refused():
    with pytest.raises(WrongFccFile, match="release"):
        release_of("signal/fcc/x/coverage.zip")
