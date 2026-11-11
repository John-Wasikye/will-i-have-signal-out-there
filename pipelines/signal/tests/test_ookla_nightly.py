"""Tests for the nightly Ookla step (C13 part 1): load a new quarter's Arizona tiles once.

Most nights there is nothing new, so the check needs no Spark: a quarter counts as loaded once
its manifest is in the raw bucket, and the manifest is kept only after the lake write, so a night
that fails part way loads the quarter again. No test calls Ookla or AWS.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ookla_tiles import Quarter, quarter_prefix, store_quarter_manifest
from signal_nightly import load_ookla_quarter, ookla_quarter_to_load
from test_ookla_tiles import (
    DENVER,
    GRAND_CANYON,
    PHOENIX,
    FakeOokla,
    _parquet_bytes,
    _source_table,
)
from test_signal_nightly import FakeS3, FakeSpark

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NOW = datetime(2026, 11, 12, 10, 3, tzinfo=UTC)
RUN_DATE = date(2026, 11, 12)
Q2, Q3 = Quarter(2026, 2), Quarter(2026, 3)


def _load(spark, s3, files, tmp_path):
    return load_ookla_quarter(
        spark,
        s3,
        "raw",
        Q3,
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace="portfolio_dev",
        now_utc=NOW,
        work_dir=tmp_path,
        opener=FakeOokla(files),
    )


def test_a_new_quarter_is_returned_for_loading():
    ookla = FakeOokla({Q3.url: b"file", Q2.url: b"file"})

    assert ookla_quarter_to_load(FakeS3(), "raw", RUN_DATE, opener=ookla) == Q3


def test_a_quarter_with_a_kept_manifest_is_not_loaded_again():
    s3 = FakeS3()
    store_quarter_manifest(
        s3,
        "raw",
        {"quarter": "2026-Q3", "source_url": Q3.url, "fetched_at_utc": "2026-11-11T10:03:00Z"},
    )

    assert ookla_quarter_to_load(s3, "raw", RUN_DATE, opener=FakeOokla({Q3.url: b"f"})) is None


def test_an_older_quarters_manifest_does_not_hide_a_new_quarter():
    s3 = FakeS3()
    store_quarter_manifest(
        s3,
        "raw",
        {"quarter": "2026-Q2", "source_url": Q2.url, "fetched_at_utc": "2026-08-01T10:03:00Z"},
    )

    assert ookla_quarter_to_load(s3, "raw", RUN_DATE, opener=FakeOokla({Q3.url: b"f"})) == Q3


def test_a_quarter_is_loaded_into_ookla_tile_for_the_run_date(tmp_path):
    spark, s3 = FakeSpark(), FakeS3()
    body = _parquet_bytes(_source_table([GRAND_CANYON, DENVER, PHOENIX]))

    result = _load(spark, s3, {Q3.url: body}, tmp_path)

    rows = spark.written["ookla_tile"]
    assert [row["tile_key"] for row in rows] == [GRAND_CANYON["quadkey"], PHOENIX["quadkey"]]
    assert {row["run_date"] for row in rows} == {RUN_DATE}
    assert {row["quarter"] for row in rows} == {"2026-Q3"}
    assert result == {"changed": True, "quarter": "2026-Q3", "tiles": 2, "tests": 3 + 5}


def test_the_manifest_is_kept_after_the_load(tmp_path):
    spark, s3 = FakeSpark(), FakeS3()
    body = _parquet_bytes(_source_table([GRAND_CANYON]))

    _load(spark, s3, {Q3.url: body}, tmp_path)

    (key,) = [key for key in s3.objects if key.startswith(quarter_prefix(Q3))]
    assert json.loads(s3.objects[key])["size_bytes"] == len(body)


def test_the_downloaded_file_is_removed_after_the_load(tmp_path):
    """The worldwide file is about 190 MB, so it does not stay on the box."""
    body = _parquet_bytes(_source_table([GRAND_CANYON]))

    _load(FakeSpark(), FakeS3(), {Q3.url: body}, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_a_quarter_with_no_arizona_tiles_stops_without_a_manifest(tmp_path):
    """No Arizona tiles at all means the file changed shape, not that Arizona had no tests."""
    s3 = FakeS3()
    body = _parquet_bytes(_source_table([DENVER]))

    with pytest.raises(ValueError, match="ookla_tile"):
        _load(FakeSpark(), s3, {Q3.url: body}, tmp_path)
    assert s3.objects == {}


def test_a_failed_lake_write_keeps_no_manifest_so_the_next_night_tries_again(tmp_path):
    class BrokenSpark(FakeSpark):
        def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
            raise RuntimeError("the lake is unreachable")

    s3 = FakeS3()
    body = _parquet_bytes(_source_table([GRAND_CANYON]))

    with pytest.raises(RuntimeError, match="unreachable"):
        _load(BrokenSpark(), s3, {Q3.url: body}, tmp_path)
    assert s3.objects == {}
