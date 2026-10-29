"""Tests for orbit ingest (C1): pull the CelesTrak Starlink list, keep the raw file unchanged with
its hash, check it against the contract, and shape the rows for the lake table.

No test calls CelesTrak or AWS: the HTTP call and the S3 client are fakes.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from contract_diff import BreakingSchemaChange
from orbit_ingest import (
    CELESTRAK_STARLINK_URL,
    FetchRefused,
    RawFile,
    fetch_gp_json,
    lake_rows,
    load_gp_partition,
    parse_gp_records,
    raw_key,
    store_raw,
)

CONTRACT = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts" / "celestrak_gp.yaml"
FETCHED_AT = datetime(2026, 10, 28, 2, 44, 7, tzinfo=UTC)

# Two element sets with the 17 fields the first-run check found (OQ-20). Values are made up.
RECORDS = [
    {
        "OBJECT_NAME": "STARLINK-90001 [DTC]",
        "OBJECT_ID": "2025-001A",
        "EPOCH": "2026-10-27T06:00:04.000320",
        "MEAN_MOTION": 15.71,
        "ECCENTRICITY": 0.0001,
        "INCLINATION": 53.05,
        "RA_OF_ASC_NODE": 120.5,
        "ARG_OF_PERICENTER": 90.1,
        "MEAN_ANOMALY": 270.2,
        "EPHEMERIS_TYPE": 0,
        "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": 90001,
        "ELEMENT_SET_NO": 999,
        "REV_AT_EPOCH": 1234,
        "BSTAR": 0.00012,
        "MEAN_MOTION_DOT": 0.0001,
        "MEAN_MOTION_DDOT": 0,
    },
    {
        "OBJECT_NAME": "STARLINK-90002",
        "OBJECT_ID": "2025-001B",
        "EPOCH": "2026-10-27T07:30:00",
        "MEAN_MOTION": 15.06,
        "ECCENTRICITY": 0.00015,
        "INCLINATION": 43.0,
        "RA_OF_ASC_NODE": 10.0,
        "ARG_OF_PERICENTER": 80.0,
        "MEAN_ANOMALY": 280.0,
        "EPHEMERIS_TYPE": 0,
        "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": 90002,
        "ELEMENT_SET_NO": 999,
        "REV_AT_EPOCH": 4321,
        "BSTAR": -0.0001,
        "MEAN_MOTION_DOT": -0.00002,
        "MEAN_MOTION_DDOT": 0,
    },
]
PAYLOAD = json.dumps(RECORDS).encode()


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, status: int = 200, body: bytes = PAYLOAD):
        self.calls = []
        self._response = FakeResponse(status, body)

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        return self._response


class S3Error(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        if IfNoneMatch == "*" and (Bucket, Key) in self.objects:
            raise S3Error("PreconditionFailed")
        self.objects[(Bucket, Key)] = (Body, ContentType)


def test_fetch_returns_the_body_and_the_fetch_time():
    opener = FakeOpener()
    raw = fetch_gp_json(CELESTRAK_STARLINK_URL, None, now_utc=FETCHED_AT, opener=opener)
    assert raw == RawFile(body=PAYLOAD, url=CELESTRAK_STARLINK_URL, fetched_at=FETCHED_AT)
    assert opener.calls == [(CELESTRAK_STARLINK_URL, 60)]


def test_the_url_is_the_one_the_first_run_check_confirmed():
    assert CELESTRAK_STARLINK_URL == (
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"
    )


def test_fetch_stops_on_any_status_other_than_200():
    with pytest.raises(FetchRefused, match="HTTP 403"):
        fetch_gp_json(CELESTRAK_STARLINK_URL, None, now_utc=FETCHED_AT, opener=FakeOpener(403))


def test_fetch_stops_on_an_empty_body():
    with pytest.raises(FetchRefused, match="empty"):
        fetch_gp_json(CELESTRAK_STARLINK_URL, None, now_utc=FETCHED_AT, opener=FakeOpener(200, b""))


def test_fetch_refuses_a_second_call_within_two_hours_without_calling_celestrak():
    opener = FakeOpener()
    last = FETCHED_AT - timedelta(hours=1, minutes=59)
    with pytest.raises(FetchRefused, match="2 hours"):
        fetch_gp_json(CELESTRAK_STARLINK_URL, last, now_utc=FETCHED_AT, opener=opener)
    assert opener.calls == []


def test_fetch_is_allowed_two_hours_after_the_last_one():
    last = FETCHED_AT - timedelta(hours=2)
    raw = fetch_gp_json(CELESTRAK_STARLINK_URL, last, now_utc=FETCHED_AT, opener=FakeOpener())
    assert raw.body == PAYLOAD


def test_fetch_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        fetch_gp_json(
            CELESTRAK_STARLINK_URL, None, now_utc=datetime(2026, 10, 28), opener=FakeOpener()
        )


def test_raw_key_names_the_source_and_the_fetch_time():
    assert (
        raw_key(FETCHED_AT) == "signal/celestrak/gp/fetched_at=2026-10-28T02:44:07Z/starlink.json"
    )


def test_store_raw_writes_the_file_unchanged_and_a_manifest_with_its_hash():
    s3 = FakeS3()
    raw = RawFile(body=PAYLOAD, url=CELESTRAK_STARLINK_URL, fetched_at=FETCHED_AT)
    manifest = store_raw(s3, "raw-bucket", raw)
    key = raw_key(FETCHED_AT)
    assert s3.objects[("raw-bucket", key)] == (PAYLOAD, "application/json")
    assert manifest == {
        "source_url": CELESTRAK_STARLINK_URL,
        "fetched_at_utc": "2026-10-28T02:44:07Z",
        "content_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        "size_bytes": len(PAYLOAD),
        "raw_key": key,
    }
    body, content_type = s3.objects[("raw-bucket", key.replace("starlink.json", "manifest.json"))]
    assert json.loads(body) == manifest
    assert content_type == "application/json"


def test_store_raw_never_replaces_a_raw_file():
    s3 = FakeS3()
    raw = RawFile(body=PAYLOAD, url=CELESTRAK_STARLINK_URL, fetched_at=FETCHED_AT)
    store_raw(s3, "raw-bucket", raw)
    with pytest.raises(S3Error):
        store_raw(s3, "raw-bucket", raw)


def test_parse_accepts_records_that_match_the_contract():
    assert parse_gp_records(PAYLOAD, CONTRACT) == RECORDS


def test_parse_stops_when_a_contract_field_is_missing():
    renamed = [{("SATNAME" if k == "OBJECT_NAME" else k): v for k, v in r.items()} for r in RECORDS]
    with pytest.raises(BreakingSchemaChange, match="removed OBJECT_NAME"):
        parse_gp_records(json.dumps(renamed).encode(), CONTRACT)


def test_parse_stops_when_a_field_changes_type():
    changed = [{**r, "NORAD_CAT_ID": str(r["NORAD_CAT_ID"])} for r in RECORDS]
    with pytest.raises(BreakingSchemaChange, match="NORAD_CAT_ID changed from integer to string"):
        parse_gp_records(json.dumps(changed).encode(), CONTRACT)


def test_parse_refuses_a_body_that_is_not_a_list():
    with pytest.raises(ValueError, match="list"):
        parse_gp_records(b'{"error": "too many requests"}', CONTRACT)


def test_lake_rows_rename_to_the_contract_columns_and_add_the_manifest():
    s3 = FakeS3()
    manifest = store_raw(
        s3, "raw-bucket", RawFile(body=PAYLOAD, url=CELESTRAK_STARLINK_URL, fetched_at=FETCHED_AT)
    )
    rows = lake_rows(RECORDS, manifest, CONTRACT)
    assert rows[0] == {
        "norad_cat_id": 90001,
        "epoch_utc": datetime(2026, 10, 27, 6, 0, 4, 320, tzinfo=UTC),
        "object_name": "STARLINK-90001 [DTC]",
        "inclination_deg": 53.05,
        "mean_motion_rev_per_day": 15.71,
        "eccentricity": 0.0001,
        "ra_of_asc_node_deg": 120.5,
        "arg_of_pericenter_deg": 90.1,
        "mean_anomaly_deg": 270.2,
        "bstar": 0.00012,
        "source_url": CELESTRAK_STARLINK_URL,
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
    }
    assert rows[1]["epoch_utc"] == datetime(2026, 10, 27, 7, 30, tzinfo=UTC)


class FakeWriter:
    def __init__(self, calls):
        self.calls = calls

    def partitionedBy(self, column):  # noqa: N802, Spark method name
        self.calls.append(f"partitionedBy:{column}")
        return self

    def create(self):
        self.calls.append("create")

    def overwritePartitions(self):  # noqa: N802, Spark method name
        self.calls.append("overwritePartitions")


class FakeFrame:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def writeTo(self, name):  # noqa: N802, Spark method name
        self.calls.append(f"writeTo:{name}")
        return FakeWriter(self.calls)


class FakeSpark:
    def __init__(self, table_exists: bool):
        self.calls = []
        self.frames = []
        exists = table_exists

        class Catalog:
            def tableExists(self, name):  # noqa: N802, Spark method name
                return exists

        self.catalog = Catalog()

    def createDataFrame(self, rows, schema=None):  # noqa: N802, Spark method name
        frame = FakeFrame(rows, self.calls)
        self.frames.append(frame)
        return frame


def _rows():
    manifest = {
        "source_url": CELESTRAK_STARLINK_URL,
        "fetched_at_utc": "2026-10-28T02:44:07Z",
        "content_sha256": "0" * 64,
    }
    return lake_rows(RECORDS, manifest, CONTRACT)


def test_first_load_creates_the_table_partitioned_by_run_date():
    spark = FakeSpark(table_exists=False)
    written = load_gp_partition(
        spark, _rows(), date(2026, 10, 28), contract_path=CONTRACT, namespace="portfolio_dev"
    )
    assert written == 2
    assert spark.calls == [
        "writeTo:portfolio.portfolio_dev.celestrak_gp",
        "partitionedBy:run_date",
        "create",
    ]
    assert {row["run_date"] for row in spark.frames[0].rows} == {date(2026, 10, 28)}


def test_a_rerun_overwrites_only_its_partition():
    spark = FakeSpark(table_exists=True)
    load_gp_partition(
        spark, _rows(), date(2026, 10, 28), contract_path=CONTRACT, namespace="portfolio_dev"
    )
    assert spark.calls == ["writeTo:portfolio.portfolio_dev.celestrak_gp", "overwritePartitions"]


def test_load_refuses_no_rows():
    with pytest.raises(ValueError, match="no rows"):
        load_gp_partition(
            FakeSpark(False), [], date(2026, 10, 28), contract_path=CONTRACT, namespace="p"
        )
