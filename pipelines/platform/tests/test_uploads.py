"""Tests for uploading the pipeline's outputs from the box to S3.

The session box is switched off most of the time, so nothing is live until its outputs are in
S3: the published Parquet files and status.json in the site bucket (read by the API and the
status page), and the run metrics and incident records in the lake bucket. These tests use a
fake S3 client, so no AWS call is made.
"""

import pytest
from uploads import OutputLocations, upload_outputs, upload_tree


class FakeS3:
    """Records every upload as (bucket, key, content type)."""

    def __init__(self):
        self.uploads: list[tuple[str, str, str | None]] = []

    def upload_file(self, Filename: str, Bucket: str, Key: str, ExtraArgs=None):  # noqa: N803
        content_type = (ExtraArgs or {}).get("ContentType")
        self.uploads.append((Bucket, Key, content_type))


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
