"""Tests for reading back what the raw store kept: the newest pull's manifest, and a raw file.

The S3 client is a fake that keeps objects in a dictionary.
"""

import json

from raw_store import latest_manifest, read_raw

PREFIX = "signal/celestrak/gp"


class FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        found = sorted(key for key in self.objects if key.startswith(Prefix))
        # S3 lists at most 1,000 keys a page, so the newest can be on a later page.
        for start in range(0, len(found), 2):
            yield {"Contents": [{"Key": key} for key in found[start : start + 2]]}
        if not found:
            yield {}

    def get_object(self, Bucket, Key):  # noqa: N803, boto3 parameter names
        return {"Body": _Body(self.objects[Key])}


class _Body:
    def __init__(self, data: bytes):
        self.data = data

    def read(self) -> bytes:
        return self.data


def _manifest(fetched_at: str) -> dict:
    return {"fetched_at_utc": fetched_at, "raw_key": f"{PREFIX}/fetched_at={fetched_at}/x.json"}


def _stored(*fetch_times: str) -> dict[str, bytes]:
    objects = {}
    for fetched_at in fetch_times:
        folder = f"{PREFIX}/fetched_at={fetched_at}"
        objects[f"{folder}/starlink.json"] = b"[]"
        objects[f"{folder}/manifest.json"] = json.dumps(_manifest(fetched_at)).encode()
    return objects


def test_the_newest_manifest_is_found_across_listing_pages():
    s3 = FakeS3(_stored("2026-10-27T10:01:00Z", "2026-10-29T10:01:00Z", "2026-10-28T10:01:00Z"))

    assert latest_manifest(s3, "raw", PREFIX) == _manifest("2026-10-29T10:01:00Z")


def test_no_earlier_pull_means_no_manifest():
    assert latest_manifest(FakeS3(), "raw", PREFIX) is None


def test_only_manifests_count_not_the_raw_files_beside_them():
    s3 = FakeS3(_stored("2026-10-28T10:01:00Z"))
    s3.objects[f"{PREFIX}/fetched_at=2026-10-29T10:01:00Z/starlink.json"] = b"[]"

    assert latest_manifest(s3, "raw", PREFIX) == _manifest("2026-10-28T10:01:00Z")


def test_a_raw_file_is_read_back_unchanged():
    s3 = FakeS3({"signal/x/starlink.json": b'[{"a": 1}]'})

    assert read_raw(s3, "raw", "signal/x/starlink.json") == b'[{"a": 1}]'
