"""Tests for the steps of the Phase A nightly run, as the DAG calls them.

CelesTrak, the NPS service, S3 and Spark are fakes. The sample CelesTrak records and NPS pages
come from the loader tests, so both test files use the same data.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from contract_diff import BreakingSchemaChange
from orbit_ingest import CELESTRAK_STARLINK_URL
from signal_nightly import (
    check_orbit_schema,
    load_orbits,
    load_trails_if_changed,
    pull_orbits,
    select_and_load_dtc,
)
from test_orbit_ingest import RECORDS
from test_trail_loader import TRAILS, _page

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
NOW = datetime(2026, 10, 29, 10, 1, tzinfo=UTC)
RUN_DATE = date(2026, 10, 29)
NAMESPACE = "portfolio_dev"


class FakeResponse:
    def __init__(self, body: bytes):
        self.status = 200
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, body: bytes):
        self.body = body
        self.urls = []

    def __call__(self, url, timeout):
        self.urls.append(url)
        return FakeResponse(self.body)


class FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        if IfNoneMatch == "*" and Key in self.objects:
            raise RuntimeError("PreconditionFailed")
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803, boto3 parameter names
        return {"Body": FakeResponse(self.objects[Key])}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        found = [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)]
        yield {"Contents": found} if found else {}


class FakeSpark:
    """Records what each table was given. ``loaded`` answers the query for loaded page hashes."""

    def __init__(self, existing=(), loaded=()):
        self.existing = set(existing)
        self.loaded = list(loaded)
        self.written: dict[str, list[dict]] = {}
        self.statements: list[str] = []
        spark = self

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return name in spark.existing

        self.catalog = Catalog()

    def sql(self, statement):
        self.statements.append(statement)
        rows = [{"content_sha256": value} for value in self.loaded]
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

        class Frame:
            def writeTo(self, name):  # noqa: N802, Spark method name
                return Writer(name)

        return Frame()


def _pulled(s3: FakeS3, at: datetime) -> dict:
    """Store a CelesTrak pull made at ``at`` as the orbit step does; return its manifest."""
    return pull_orbits(s3, "raw", now_utc=at, opener=FakeOpener(json.dumps(RECORDS).encode()))


def test_the_first_pull_calls_celestrak_and_keeps_the_file():
    s3 = FakeS3()
    opener = FakeOpener(json.dumps(RECORDS).encode())

    manifest = pull_orbits(s3, "raw", now_utc=NOW, opener=opener)

    assert opener.urls == [CELESTRAK_STARLINK_URL]
    assert manifest["fetched_at_utc"] == "2026-10-29T10:01:00Z"
    assert s3.objects[manifest["raw_key"]] == json.dumps(RECORDS).encode()


def test_a_pull_within_two_hours_is_reused_without_calling_celestrak():
    # A retry, or a run cleared and run again, must not pull CelesTrak twice in 2 hours.
    s3 = FakeS3()
    first = _pulled(s3, NOW)
    opener = FakeOpener(b"[]")

    again = pull_orbits(s3, "raw", now_utc=NOW + timedelta(minutes=110), opener=opener)

    assert again == first
    assert opener.urls == []


def test_a_pull_older_than_two_hours_is_replaced_by_a_new_one():
    s3 = FakeS3()
    _pulled(s3, NOW - timedelta(days=1))
    opener = FakeOpener(json.dumps(RECORDS).encode())

    manifest = pull_orbits(s3, "raw", now_utc=NOW, opener=opener)

    assert opener.urls == [CELESTRAK_STARLINK_URL]
    assert manifest["fetched_at_utc"] == "2026-10-29T10:01:00Z"


def test_the_schema_check_counts_the_records_of_a_good_file():
    s3 = FakeS3()
    manifest = _pulled(s3, NOW)

    assert check_orbit_schema(s3, "raw", manifest, CONTRACTS) == len(RECORDS)


def test_the_schema_check_stops_on_a_changed_field():
    s3 = FakeS3()
    changed = [{**record, "NORAD_CAT_ID": str(record["NORAD_CAT_ID"])} for record in RECORDS]
    manifest = pull_orbits(s3, "raw", now_utc=NOW, opener=FakeOpener(json.dumps(changed).encode()))

    with pytest.raises(BreakingSchemaChange, match="NORAD_CAT_ID"):
        check_orbit_schema(s3, "raw", manifest, CONTRACTS)


def test_the_orbit_load_writes_every_record_for_the_run_date():
    s3 = FakeS3()
    manifest = _pulled(s3, NOW)
    spark = FakeSpark()

    written = load_orbits(
        spark, s3, "raw", manifest, RUN_DATE, contracts_dir=CONTRACTS, namespace=NAMESPACE
    )

    assert written == len(RECORDS)
    assert [row["norad_cat_id"] for row in spark.written["celestrak_gp"]] == [90001, 90002]
    assert {row["run_date"] for row in spark.written["celestrak_gp"]} == {RUN_DATE}


def test_the_selector_writes_the_tagged_satellites_and_an_empty_disagreement_list():
    s3 = FakeS3()
    manifest = _pulled(s3, NOW)
    spark = FakeSpark()

    counts = select_and_load_dtc(
        spark, s3, "raw", manifest, RUN_DATE, contracts_dir=CONTRACTS, namespace=NAMESPACE
    )

    assert counts == {"dtc_satellite": 1, "dtc_disagreement": 0}
    assert [row["norad_cat_id"] for row in spark.written["dtc_satellite"]] == [90001]
    assert spark.written["dtc_disagreement"] == []


def _trail_opener() -> FakeOpener:
    return FakeOpener(_page(TRAILS))


def test_new_trail_pages_are_kept_and_loaded():
    s3 = FakeS3()
    spark = FakeSpark()

    result = load_trails_if_changed(
        spark,
        s3,
        "raw",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        now_utc=NOW,
        opener=_trail_opener(),
    )

    assert result["changed"] is True
    assert result["nps_trail_line"] == 3
    assert result["trail_point"] == len(spark.written["trail_point"])
    assert any(key.endswith("page-000.json") for key in s3.objects)


def test_unchanged_trail_pages_are_neither_kept_nor_loaded_again():
    # ADR 0028: reference data is recomputed only when its source's hash changes.
    loaded = hashlib.sha256(_page(TRAILS)).hexdigest()
    s3 = FakeS3()
    spark = FakeSpark(existing={f"portfolio.{NAMESPACE}.nps_trail_line"}, loaded=[loaded])

    result = load_trails_if_changed(
        spark,
        s3,
        "raw",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        now_utc=NOW,
        opener=_trail_opener(),
    )

    assert result == {"changed": False}
    assert s3.objects == {}
    assert spark.written == {}


def test_trails_are_loaded_again_when_the_last_load_was_from_other_pages():
    s3 = FakeS3()
    spark = FakeSpark(existing={f"portfolio.{NAMESPACE}.nps_trail_line"}, loaded=["0" * 64])

    result = load_trails_if_changed(
        spark,
        s3,
        "raw",
        RUN_DATE,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
        now_utc=NOW,
        opener=_trail_opener(),
    )

    assert result["changed"] is True
    assert "trail_point" in spark.written
