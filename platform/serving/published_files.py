"""Copies published Parquet files from S3 into the function's local folder.

The API reads its data with DuckDB from local files. On Lambda those files live in /tmp,
so this code fills that folder from the published folder of the site bucket. It copies
when the function starts, and again whenever the copy is older than a time limit, so a
new nightly publish reaches a function that has been running for a while.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def sync_published_files(client, bucket: str, prefix: str, target_dir: Path) -> list[Path]:  # noqa: ANN001
    """Copy each .parquet file directly under ``prefix`` into ``target_dir``.

    Files in sub-folders and files of other types are left alone. Each file is
    downloaded to a temporary name and then moved into place, so a reader never sees a
    half-written file. ``client`` is a boto3 S3 client.
    """
    if not prefix.endswith("/"):
        raise ValueError("prefix must end with a slash, for example 'published/'")

    target_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            name = item["Key"][len(prefix) :]
            if "/" in name or not name.endswith(".parquet"):
                continue
            final = target_dir / name
            partial = target_dir / f".{name}.part"
            client.download_file(Bucket=bucket, Key=item["Key"], Filename=str(partial))
            os.replace(partial, final)
            copied.append(final)
    return copied


def is_stale(last_synced: datetime | None, now: datetime, ttl_seconds: int) -> bool:
    """Return True when the files were never copied or the copy is older than the limit."""
    if last_synced is None:
        return True
    if last_synced.tzinfo is None or now.tzinfo is None:
        raise ValueError("times must be timezone-aware (UTC), got a naive datetime")
    return (now - last_synced).total_seconds() > ttl_seconds


class PublishedFilesCache:
    """Keeps the local copy of the published files fresh."""

    def __init__(self, client, bucket: str, prefix: str, target_dir: Path, ttl_seconds: int):  # noqa: ANN001
        """Set where the files come from, where they go, and how long a copy stays fresh.

        ``client`` is a boto3 S3 client. ``ttl_seconds`` is the age at which a copy counts as stale.
        """
        self.client = client
        self.bucket = bucket
        self.prefix = prefix
        self.target_dir = target_dir
        self.ttl_seconds = ttl_seconds
        self._last_synced: datetime | None = None

    def refresh_if_stale(self, now: datetime) -> None:
        """Copy the files if they were never copied or the copy is too old.

        If the copy fails, the time is not recorded, so the next request tries again.
        """
        if is_stale(self._last_synced, now, self.ttl_seconds):
            sync_published_files(self.client, self.bucket, self.prefix, self.target_dir)
            self._last_synced = now
