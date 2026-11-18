"""Tests for the nightly OpenCelliD step (C13 part 3): load the kept cell files when they change.

John keeps the files in the raw bucket by hand, one folder per mobile country code (MCC) and
fetch time. ``tower_files_to_load`` needs no Spark: it compares the newest kept file of each MCC
with the "loaded" marker the last load wrote, so most nights cost one listing. ``load_towers``
writes ``opencellid_tower`` and only then the marker, so a night that fails part way loads again.
The marker lists every loaded file, including one with no Arizona cells, whose hash never
reaches the table (the reload found on Nov 18, 2026). No test calls OpenCelliD or AWS.
"""

import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from opencellid_towers import RAW_PREFIX, WrongOpenCellidFile
from signal_nightly import load_towers, tower_files_to_load
from test_opencellid_towers import DENVER, GRAND_CANYON, HEADER, PHOENIX
from test_signal_nightly import FakeS3, FakeSpark

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
RUN_DATE = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 10, 9, tzinfo=UTC)


def _keep(s3, mcc, fetched_at, lines, *, sha=None):
    """Keep a gzip export and its manifest the way John's helper does; return the hash."""
    body = gzip.compress(("\n".join(lines) + "\n").encode())
    folder = f"{RAW_PREFIX}/mcc={mcc}/fetched_at={fetched_at}"
    digest = sha or hashlib.sha256(body).hexdigest()
    s3.objects[f"{folder}/{mcc}.csv.gz"] = body
    s3.objects[f"{folder}/manifest.json"] = json.dumps(
        {
            "source_url": "https://opencellid.org/downloads.php",
            "mcc": mcc,
            "fetched_at_utc": fetched_at,
            "size_bytes": len(body),
            "content_sha256": digest,
            "raw_key": f"{folder}/{mcc}.csv.gz",
        }
    ).encode()
    return digest


def _load(spark, s3, manifests, now=NOW):
    return load_towers(
        spark,
        s3,
        "raw",
        manifests,
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace="portfolio_dev",
        now_utc=now,
    )


def test_nothing_is_loaded_before_a_file_is_kept():
    assert tower_files_to_load(FakeS3(), "raw") is None


def test_the_newest_file_of_each_mcc_is_returned_for_loading():
    s3 = FakeS3()
    _keep(s3, 310, "2026-08-01T09:00:00Z", [DENVER])
    newer = _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    other = _keep(s3, 311, "2026-11-18T09:01:00Z", [PHOENIX])

    manifests = tower_files_to_load(s3, "raw")

    assert [m["content_sha256"] for m in manifests] == [newer, other]


def test_the_kept_files_are_loaded_into_opencellid_tower():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [HEADER, GRAND_CANYON, DENVER])
    _keep(s3, 311, "2026-11-18T09:01:00Z", [HEADER, PHOENIX])
    spark = FakeSpark()

    result = _load(spark, s3, tower_files_to_load(s3, "raw"))

    ids = sorted(row["tower_id"] for row in spark.written["opencellid_tower"])
    assert ids == ["LTE-310-260-12345-678901", "NR-311-480-2001-90000000001"]
    assert result == {"changed": True, "files": 2, "cells": 2, "by_radio": {"LTE": 1, "NR": 1}}


def test_files_already_loaded_are_not_loaded_again():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    _load(FakeSpark(), s3, tower_files_to_load(s3, "raw"))

    assert tower_files_to_load(s3, "raw") is None


def test_a_kept_file_with_no_arizona_cells_does_not_make_every_night_reload():
    """The Nov 18, 2026 bug: 312.csv.gz has no Arizona cells, so its hash is never in the table."""
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    _keep(s3, 312, "2026-11-18T09:02:00Z", [DENVER])
    _load(FakeSpark(), s3, tower_files_to_load(s3, "raw"))

    assert tower_files_to_load(s3, "raw") is None


def test_a_newly_kept_file_is_loaded_with_the_others():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    _load(FakeSpark(), s3, tower_files_to_load(s3, "raw"))
    _keep(s3, 311, "2026-11-19T09:00:00Z", [PHOENIX])

    assert [m["mcc"] for m in tower_files_to_load(s3, "raw")] == [310, 311]


def test_loading_the_same_files_twice_in_one_second_keeps_one_marker():
    """A rerun at the same moment must not fail on the raw bucket's no-replace rule."""
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    manifests = tower_files_to_load(s3, "raw")
    _load(FakeSpark(), s3, manifests)

    _load(FakeSpark(), s3, manifests)

    assert tower_files_to_load(s3, "raw") is None


def test_a_failed_lake_write_keeps_no_marker_so_the_next_night_tries_again():
    class BrokenSpark(FakeSpark):
        def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
            raise RuntimeError("the lake is unreachable")

    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    manifests = tower_files_to_load(s3, "raw")

    with pytest.raises(RuntimeError, match="unreachable"):
        _load(BrokenSpark(), s3, manifests)
    assert tower_files_to_load(s3, "raw") == manifests


def test_a_file_whose_hash_differs_from_its_manifest_stops_the_step():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON], sha="b" * 64)

    with pytest.raises(WrongOpenCellidFile, match="hash"):
        _load(FakeSpark(), s3, tower_files_to_load(s3, "raw"))


def test_kept_files_with_no_arizona_cells_at_all_stop_the_step():
    """No Arizona cells at all means a wrong file or a changed format, not an empty state."""
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [DENVER])
    spark = FakeSpark()

    with pytest.raises(ValueError, match="opencellid_tower"):
        _load(spark, s3, tower_files_to_load(s3, "raw"))
    assert spark.written == {}


def test_the_same_cell_in_two_files_stops_the_step():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    _keep(s3, 311, "2026-11-18T09:01:00Z", [GRAND_CANYON])

    with pytest.raises(WrongOpenCellidFile, match="LTE-310-260-12345-678901"):
        _load(FakeSpark(), s3, tower_files_to_load(s3, "raw"))
