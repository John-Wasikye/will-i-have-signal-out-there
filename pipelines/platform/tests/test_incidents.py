"""Tests for incident records (docs/platform/contracts/platform_incidents.yaml).

An incident is a short record of something that really broke: what broke, when, and where.
The cause and the fix are filled in later, by hand. Free text must hold no key or address.
"""

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from incidents import (
    build_incident,
    failure_incident,
    file_incident,
    next_incident_number,
    record_failure,
    write_incident,
)

OPENED = datetime(2026, 10, 10, 10, 30, tzinfo=UTC)


def test_an_incident_has_the_contract_fields():
    incident = build_incident(
        number=3,
        opened_utc=OPENED,
        pipeline="platform_skeleton_nightly",
        what_broke="Something broke.",
    )

    assert incident == {
        "incident_id": "INC-2026-10-10-03",
        "opened_at_utc": "2026-10-10T10:30:00Z",
        "project": "platform",
        "pipeline": "platform_skeleton_nightly",
        "what_broke": "Something broke.",
        "reached_maximum_runtime": False,
        "status": "open",
    }


def test_an_incident_can_say_the_run_reached_its_maximum():
    incident = build_incident(
        number=1,
        opened_utc=OPENED,
        pipeline="p",
        what_broke="Too slow.",
        reached_maximum_runtime=True,
    )

    assert incident["reached_maximum_runtime"] is True


def test_an_incident_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_incident(1, datetime(2026, 10, 10, 10, 30), "p", "x")


def test_an_incident_refuses_a_number_below_one():
    with pytest.raises(ValueError, match="at least 1"):
        build_incident(0, OPENED, "p", "x")


def test_a_failed_task_becomes_an_incident_that_names_the_dag_and_the_task():
    incident = failure_incident(
        number=1,
        opened_utc=OPENED,
        dag_id="platform_skeleton_nightly",
        task_id="publish_sample",
        error="ValueError: bad row",
    )

    assert incident["pipeline"] == "platform_skeleton_nightly"
    assert "publish_sample" in incident["what_broke"]
    assert "ValueError: bad row" in incident["what_broke"]
    assert incident["reached_maximum_runtime"] is False


def test_a_very_long_error_is_cut_so_the_record_stays_short():
    incident = failure_incident(1, OPENED, "d", "t", error="x" * 5000)

    assert len(incident["what_broke"]) < 500


def test_an_incident_is_written_as_a_parquet_file_with_the_contract_columns(tmp_path):
    incident = build_incident(1, OPENED, "p", "Something broke.")

    path = write_incident(incident, tmp_path)

    table = pq.ParquetFile(path).read()
    assert set(table.column_names) == {
        "incident_id",
        "opened_at_utc",
        "closed_at_utc",
        "project",
        "pipeline",
        "what_broke",
        "cause",
        "fix",
        "github_issue_url",
        "reached_maximum_runtime",
        "status",
    }
    row = table.to_pylist()[0]
    assert row["incident_id"] == "INC-2026-10-10-01"
    assert row["status"] == "open"
    assert row["closed_at_utc"] is None
    assert row["cause"] is None


def test_writing_the_same_incident_twice_replaces_the_file(tmp_path):
    incident = build_incident(1, OPENED, "p", "Something broke.")

    first = write_incident(incident, tmp_path)
    second = write_incident(incident, tmp_path)

    assert first == second
    assert len(list(tmp_path.rglob("*.parquet"))) == 1


class FakeTaskInstance:
    def __init__(self, task_id: str):
        self.task_id = task_id


class S3Error(Exception):
    """Stands in for botocore's ClientError, which carries the S3 error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeLake:
    """An S3 bucket in memory: listing by prefix, and put_object with If-None-Match."""

    def __init__(self, keys=(), take_first: int = 0, fail_with: str | None = None):
        self.objects: dict[str, bytes] = {key: b"" for key in keys}
        self.take_first = take_first
        self.fail_with = fail_with

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        found = [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)]
        yield {"Contents": found} if found else {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        if self.fail_with:
            raise S3Error(self.fail_with)
        if self.take_first:
            # Another writer files the same key a moment before this one.
            self.take_first -= 1
            self.objects[Key] = b"someone else"
        if IfNoneMatch == "*" and Key in self.objects:
            raise S3Error("PreconditionFailed")
        self.objects[Key] = Body


FAILURE = {
    "dag": type("Dag", (), {"dag_id": "platform_skeleton_nightly"})(),
    "task_instance": type("TaskInstance", (), {"task_id": "publish_sample"})(),
    "exception": RuntimeError("disk full"),
}


def _row(lake: FakeLake, key: str) -> dict:
    import io

    return pq.read_table(io.BytesIO(lake.objects[key])).to_pylist()[0]


def test_the_next_number_follows_the_highest_one_used_that_day():
    taken = [
        "platform/incidents/INC-2026-10-10-01.parquet",
        "platform/incidents/INC-2026-10-10-03.parquet",
        "platform/incidents/INC-2026-10-09-07.parquet",
    ]

    assert next_incident_number(taken, OPENED) == 4


def test_the_first_incident_of_a_day_is_number_one():
    assert next_incident_number([], OPENED) == 1


def test_the_failure_callback_files_the_incident_in_s3_at_once(tmp_path):
    lake = FakeLake()

    key = record_failure(FAILURE, tmp_path, lake, "lake", now_utc=OPENED)

    assert key == "platform/incidents/INC-2026-10-10-01.parquet"
    row = _row(lake, key)
    assert row["pipeline"] == "platform_skeleton_nightly"
    assert "publish_sample" in row["what_broke"]
    assert "disk full" in row["what_broke"]


def test_the_number_comes_from_s3_so_a_new_box_does_not_reuse_one(tmp_path):
    """A replaced box starts with an empty folder, but S3 still has the day's records."""
    lake = FakeLake(["platform/incidents/INC-2026-10-10-01.parquet"])

    key = record_failure(FAILURE, tmp_path, lake, "lake", now_utc=OPENED)

    assert key == "platform/incidents/INC-2026-10-10-02.parquet"
    assert lake.objects["platform/incidents/INC-2026-10-10-01.parquet"] == b""


def test_a_record_on_the_box_that_is_not_in_s3_yet_still_counts(tmp_path):
    write_incident(build_incident(1, OPENED, "p", "Earlier."), tmp_path)

    key = record_failure(FAILURE, tmp_path, FakeLake(), "lake", now_utc=OPENED)

    assert key.endswith("INC-2026-10-10-02.parquet")


def test_when_another_writer_takes_the_number_the_next_one_is_used(tmp_path):
    lake = FakeLake(take_first=1)

    key = record_failure(FAILURE, tmp_path, lake, "lake", now_utc=OPENED)

    assert key.endswith("INC-2026-10-10-02.parquet")
    assert lake.objects["platform/incidents/INC-2026-10-10-01.parquet"] == b"someone else"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["INC-2026-10-10-02.parquet"]


def test_a_writer_that_keeps_losing_gives_up_with_an_error(tmp_path):
    with pytest.raises(RuntimeError, match="could not file"):
        file_incident(
            FakeLake(take_first=10),
            "lake",
            lambda number: build_incident(number, OPENED, "p", "x"),
            OPENED,
            tmp_path,
            attempts=3,
        )


def test_when_s3_cannot_be_reached_the_record_stays_on_the_box_for_the_nightly_upload(tmp_path):
    with pytest.raises(S3Error, match="RequestTimeout"):
        record_failure(FAILURE, tmp_path, FakeLake(fail_with="RequestTimeout"), "lake", OPENED)

    assert [path.name for path in tmp_path.iterdir()] == ["INC-2026-10-10-01.parquet"]
