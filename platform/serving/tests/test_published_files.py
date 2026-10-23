"""Tests for copying published Parquet files from S3 into the function's local folder.

The Lambda function reads files from /tmp. This code fills that folder from the published
folder of the site bucket, using a fake S3 client here so no AWS call is made.
"""

from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest
from published_files import is_stale, sync_published_files


class FakeS3:
    """Holds objects in memory and answers the two S3 calls the code makes."""

    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.downloaded: list[str] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket: str, Prefix: str):  # noqa: N803, boto3 parameter names
        keys = [key for key in self.objects if key.startswith(Prefix)]
        yield {"Contents": [{"Key": key} for key in keys]} if keys else {}

    def download_file(self, Bucket: str, Key: str, Filename: str):  # noqa: N803, boto3 names
        self.downloaded.append(Key)
        with open(Filename, "wb") as handle:
            handle.write(self.objects[Key])


def _parquet_bytes(tmp_path) -> bytes:
    import pyarrow as pa

    path = tmp_path / "source.parquet"
    pq.write_table(pa.table({"key": ["a"]}), path)
    return path.read_bytes()


def test_each_parquet_file_in_the_published_folder_is_copied(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"published/sample_answer.parquet": data, "published/other.parquet": data})
    target = tmp_path / "local"

    copied = sync_published_files(client, "bucket", "published/", target)

    assert sorted(path.name for path in copied) == ["other.parquet", "sample_answer.parquet"]
    assert pq.read_table(target / "sample_answer.parquet").num_rows == 1


def test_files_that_are_not_parquet_are_left_alone(tmp_path):
    client = FakeS3({"published/status.json": b"{}", "published/readme.txt": b"x"})

    copied = sync_published_files(client, "bucket", "published/", tmp_path / "local")

    assert copied == []
    assert client.downloaded == []


def test_files_in_other_folders_are_left_alone(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"raw/secret.parquet": data, "published/nested/deep.parquet": data})

    copied = sync_published_files(client, "bucket", "published/", tmp_path / "local")

    assert copied == []


def test_an_empty_published_folder_copies_nothing(tmp_path):
    copied = sync_published_files(FakeS3({}), "bucket", "published/", tmp_path / "local")

    assert copied == []


def test_a_second_sync_replaces_the_file_and_leaves_no_temporary_files(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"published/sample_answer.parquet": data})
    target = tmp_path / "local"

    sync_published_files(client, "bucket", "published/", target)
    sync_published_files(client, "bucket", "published/", target)

    assert [path.name for path in target.iterdir()] == ["sample_answer.parquet"]


def test_a_prefix_without_a_trailing_slash_is_refused(tmp_path):
    with pytest.raises(ValueError, match="end with a slash"):
        sync_published_files(FakeS3({}), "bucket", "published", tmp_path / "local")


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def test_data_that_was_never_synced_is_stale():
    assert is_stale(None, NOW, ttl_seconds=300) is True


def test_data_synced_a_minute_ago_is_fresh():
    assert is_stale(NOW - timedelta(seconds=60), NOW, ttl_seconds=300) is False


def test_data_synced_longer_ago_than_the_limit_is_stale():
    assert is_stale(NOW - timedelta(seconds=301), NOW, ttl_seconds=300) is True


def test_stale_check_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        is_stale(datetime(2026, 10, 10, 11, 0), NOW, ttl_seconds=300)


def _cache(client, tmp_path, ttl_seconds=300):
    from published_files import PublishedFilesCache

    return PublishedFilesCache(
        client=client,
        bucket="bucket",
        prefix="published/",
        target_dir=tmp_path / "local",
        ttl_seconds=ttl_seconds,
    )


def test_the_first_refresh_copies_the_files(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"published/sample_answer.parquet": data})

    _cache(client, tmp_path).refresh_if_stale(NOW)

    assert client.downloaded == ["published/sample_answer.parquet"]


def test_a_refresh_inside_the_time_limit_does_nothing(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"published/sample_answer.parquet": data})
    cache = _cache(client, tmp_path)

    cache.refresh_if_stale(NOW)
    cache.refresh_if_stale(NOW + timedelta(seconds=60))

    assert client.downloaded == ["published/sample_answer.parquet"]


def test_a_refresh_after_the_time_limit_copies_the_files_again(tmp_path):
    data = _parquet_bytes(tmp_path)
    client = FakeS3({"published/sample_answer.parquet": data})
    cache = _cache(client, tmp_path)

    cache.refresh_if_stale(NOW)
    cache.refresh_if_stale(NOW + timedelta(seconds=301))

    assert client.downloaded == ["published/sample_answer.parquet"] * 2


def test_a_failed_copy_is_tried_again_on_the_next_request(tmp_path):
    class BrokenS3(FakeS3):
        def paginate(self, Bucket: str, Prefix: str):  # noqa: N803, boto3 parameter names
            raise OSError("network down")

    cache = _cache(BrokenS3({}), tmp_path)

    with pytest.raises(OSError, match="network down"):
        cache.refresh_if_stale(NOW)

    working = FakeS3({"published/sample_answer.parquet": _parquet_bytes(tmp_path)})
    cache.client = working
    cache.refresh_if_stale(NOW + timedelta(seconds=1))

    assert working.downloaded == ["published/sample_answer.parquet"]
