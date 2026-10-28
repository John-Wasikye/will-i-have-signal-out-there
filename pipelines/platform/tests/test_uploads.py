"""Tests for uploading the pipeline's outputs from the box to S3.

The session box is switched off most of the time, so nothing is live until its outputs are in
S3: the published Parquet files and status.json in the site bucket (read by the API and the
status page), and the run metrics and incident records in the lake bucket. These tests use a
fake S3 client, so no AWS call is made.
"""

import pytest
from uploads import OutputLocations, upload_new_files, upload_outputs, upload_tree


class S3Error(Exception):
    """Stands in for botocore's ClientError, which carries the S3 error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    """Records every upload as (bucket, key, content type), and keeps what each key holds.

    put_object honours ``IfNoneMatch="*"`` the way S3 does: it refuses a key that exists.
    """

    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None, fail_with=None):
        self.uploads: list[tuple[str, str, str | None]] = []
        self.objects = dict(objects or {})
        self.conditions: list[str | None] = []
        self.fail_with = fail_with

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs=None):  # noqa: N803
        content_type = (ExtraArgs or {}).get("ContentType")
        self.uploads.append((Bucket, Key, content_type))
        with open(Filename, "rb") as file:
            self.objects[(Bucket, Key)] = file.read()

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        if self.fail_with:
            raise S3Error(self.fail_with)
        self.conditions.append(IfNoneMatch)
        if IfNoneMatch == "*" and (Bucket, Key) in self.objects:
            raise S3Error("PreconditionFailed")
        self.uploads.append((Bucket, Key, ContentType))
        self.objects[(Bucket, Key)] = Body


def _write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_every_file_goes_up_under_the_prefix_with_its_relative_path(tmp_path):
    _write(tmp_path / "a.parquet")
    _write(tmp_path / "dag_id=d" / "run_id=r" / "b.parquet")
    s3 = FakeS3()

    keys = upload_tree(s3, "bucket", "platform/run_metrics/", tmp_path)

    assert sorted(keys) == [
        "platform/run_metrics/a.parquet",
        "platform/run_metrics/dag_id=d/run_id=r/b.parquet",
    ]
    assert sorted(key for _, key, _ in s3.uploads) == sorted(keys)


def test_temporary_files_are_not_uploaded(tmp_path):
    _write(tmp_path / "good.parquet")
    _write(tmp_path / ".good.parquet.part")
    _write(tmp_path / ".staging" / "half.parquet")
    _write(tmp_path / "status.json.tmp")
    s3 = FakeS3()

    keys = upload_tree(s3, "bucket", "p/", tmp_path)

    assert keys == ["p/good.parquet"]


def test_a_missing_folder_uploads_nothing_and_is_not_an_error(tmp_path):
    assert upload_tree(FakeS3(), "bucket", "p/", tmp_path / "does-not-exist") == []


def test_the_prefix_must_end_with_a_slash(tmp_path):
    with pytest.raises(ValueError, match="end with a slash"):
        upload_tree(FakeS3(), "bucket", "p", tmp_path)


def test_parquet_and_json_files_get_the_right_content_type(tmp_path):
    _write(tmp_path / "t.parquet")
    _write(tmp_path / "s.json")
    s3 = FakeS3()

    upload_tree(s3, "bucket", "p/", tmp_path)

    types = {key: content_type for _, key, content_type in s3.uploads}
    assert types["p/t.parquet"] == "application/vnd.apache.parquet"
    assert types["p/s.json"] == "application/json"


LOCATIONS = OutputLocations(site_bucket="site-bucket", lake_bucket="lake-bucket")


def test_each_output_goes_to_the_bucket_and_folder_that_reads_it(tmp_path):
    published, metrics, incidents = tmp_path / "pub", tmp_path / "met", tmp_path / "inc"
    _write(published / "sample_answer.parquet")
    _write(published / "status.json", "{}")
    _write(metrics / "dag_id=d" / "m.parquet")
    _write(incidents / "INC-2026-10-10-01.parquet")
    s3 = FakeS3()

    upload_outputs(s3, LOCATIONS, published, metrics, incidents)

    assert sorted((bucket, key) for bucket, key, _ in s3.uploads) == [
        ("lake-bucket", "platform/incidents/INC-2026-10-10-01.parquet"),
        ("lake-bucket", "platform/run_metrics/dag_id=d/m.parquet"),
        ("site-bucket", "published/sample_answer.parquet"),
        ("site-bucket", "status.json"),
    ]


def test_status_json_is_at_the_site_root_and_never_under_published(tmp_path):
    published = tmp_path / "pub"
    _write(published / "status.json", "{}")
    s3 = FakeS3()

    upload_outputs(s3, LOCATIONS, published, tmp_path / "m", tmp_path / "i")

    assert s3.uploads == [("site-bucket", "status.json", "application/json")]


def test_the_status_file_goes_up_last_so_the_page_never_points_at_missing_data(tmp_path):
    published = tmp_path / "pub"
    _write(published / "status.json", "{}")
    _write(published / "sample_answer.parquet")
    s3 = FakeS3()

    upload_outputs(s3, LOCATIONS, published, tmp_path / "m", tmp_path / "i")

    assert s3.uploads[-1][1] == "status.json"


def test_a_new_file_goes_up_only_on_the_condition_that_the_key_is_free(tmp_path):
    _write(tmp_path / "INC-2026-10-10-01.parquet", "open")
    s3 = FakeS3()

    keys = upload_new_files(s3, "lake", "platform/incidents/", tmp_path)

    assert keys == ["platform/incidents/INC-2026-10-10-01.parquet"]
    assert s3.conditions == ["*"]
    assert s3.objects[("lake", keys[0])] == b"open"


def test_a_file_already_in_s3_is_never_replaced_by_the_copy_on_the_box(tmp_path):
    """A record closed in S3 must not go back to open when the box uploads its old copy."""
    key = "platform/incidents/INC-2026-10-10-01.parquet"
    _write(tmp_path / "INC-2026-10-10-01.parquet", "open")
    s3 = FakeS3({("lake", key): b"closed"})

    keys = upload_new_files(s3, "lake", "platform/incidents/", tmp_path)

    assert keys == []
    assert s3.objects[("lake", key)] == b"closed"


def test_any_other_s3_error_still_stops_the_upload(tmp_path):
    _write(tmp_path / "INC-2026-10-10-01.parquet")

    with pytest.raises(S3Error, match="AccessDenied"):
        upload_new_files(FakeS3(fail_with="AccessDenied"), "lake", "p/", tmp_path)


def test_the_nightly_upload_never_replaces_an_incident_record_in_s3(tmp_path):
    key = "platform/incidents/INC-2026-10-10-01.parquet"
    incidents = tmp_path / "inc"
    _write(incidents / "INC-2026-10-10-01.parquet", "open")
    s3 = FakeS3({("lake-bucket", key): b"closed"})

    upload_outputs(s3, LOCATIONS, tmp_path / "pub", tmp_path / "met", incidents)

    assert s3.objects[("lake-bucket", key)] == b"closed"
