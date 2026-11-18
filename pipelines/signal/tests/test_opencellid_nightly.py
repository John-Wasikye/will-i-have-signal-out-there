"""Tests for the nightly OpenCelliD step (C13 part 3): load the kept cell files when they change.

John keeps the files in the raw bucket by hand, one folder per mobile country code (MCC) and
fetch time. The step loads the newest file of each MCC, and only when the kept set differs from
the loaded one (ADR 0028). Before the first file is kept, the step does nothing. No test calls
OpenCelliD or AWS.
"""

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from opencellid_towers import RAW_PREFIX, WrongOpenCellidFile
from signal_nightly import load_towers_if_changed
from test_opencellid_towers import DENVER, GRAND_CANYON, HEADER, PHOENIX
from test_signal_nightly import FakeS3, FakeSpark

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
RUN_DATE = date(2026, 11, 18)
TABLE = "portfolio.portfolio_dev.opencellid_tower"


def _keep(s3, mcc, fetched_at, lines, *, sha=None):
    """Keep a gzip export and its manifest the way John's helper does; return the hash."""
    body = gzip.compress(("\n".join(lines) + "\n").encode())
    folder = f"{RAW_PREFIX}/mcc={mcc}/fetched_at={fetched_at}"
    digest = sha or hashlib.sha256(body).hexdigest()
    s3.objects[f"{folder}/{mcc}.csv.gz"] = body
    s3.objects[f"{folder}/manifest.json"] = json.dumps(
        {
            "source_url": f"https://opencellid.org/downloads.php#{mcc}.csv.gz",
            "mcc": mcc,
            "fetched_at_utc": fetched_at,
            "size_bytes": len(body),
            "content_sha256": digest,
            "raw_key": f"{folder}/{mcc}.csv.gz",
        }
    ).encode()
    return digest


def _load(spark, s3):
    return load_towers_if_changed(
        spark, s3, "raw", RUN_DATE, contracts_dir=CONTRACTS, namespace="portfolio_dev"
    )


def test_nothing_happens_before_a_file_is_kept():
    spark = FakeSpark()

    assert _load(spark, FakeS3()) == {"changed": False, "files": 0}
    assert spark.written == {}


def test_the_newest_file_of_each_mcc_is_loaded():
    s3 = FakeS3()
    _keep(s3, 310, "2026-08-01T09:00:00Z", [HEADER, DENVER])
    _keep(s3, 310, "2026-11-18T09:00:00Z", [HEADER, GRAND_CANYON, DENVER])
    _keep(s3, 311, "2026-11-18T09:01:00Z", [HEADER, PHOENIX])
    spark = FakeSpark()

    result = _load(spark, s3)

    ids = sorted(row["tower_id"] for row in spark.written["opencellid_tower"])
    assert ids == ["LTE-310-260-12345-678901", "NR-311-480-2001-90000000001"]
    assert result == {"changed": True, "files": 2, "cells": 2, "by_radio": {"LTE": 1, "NR": 1}}


def test_files_already_loaded_are_not_loaded_again():
    s3 = FakeS3()
    digest = _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    spark = FakeSpark(existing={TABLE}, loaded=[digest])

    assert _load(spark, s3) == {"changed": False, "files": 1}
    assert spark.written == {}


def test_a_file_whose_hash_differs_from_its_manifest_stops_the_step():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON], sha="b" * 64)

    with pytest.raises(WrongOpenCellidFile, match="hash"):
        _load(FakeSpark(), s3)


def test_kept_files_with_no_arizona_cells_stop_the_step():
    """No Arizona cells at all means a wrong file or a changed format, not an empty state."""
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [DENVER])
    spark = FakeSpark()

    with pytest.raises(ValueError, match="opencellid_tower"):
        _load(spark, s3)
    assert spark.written == {}


def test_the_same_cell_in_two_files_stops_the_step():
    s3 = FakeS3()
    _keep(s3, 310, "2026-11-18T09:00:00Z", [GRAND_CANYON])
    _keep(s3, 311, "2026-11-18T09:01:00Z", [GRAND_CANYON])

    with pytest.raises(WrongOpenCellidFile, match="LTE-310-260-12345-678901"):
        _load(FakeSpark(), s3)
