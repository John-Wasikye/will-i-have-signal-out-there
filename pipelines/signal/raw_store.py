"""Download a source file and keep it unchanged in the raw bucket (engineering standard 1).

Every source pull goes through here, so each raw file gets the same treatment: a download that
stops on any status other than HTTP 200 or an empty body, and a write that keeps the file byte
for byte beside a manifest of URL, fetch time, size and SHA-256 hash. Writes use If-None-Match,
so a raw file is never replaced (live raw files are also locked for 30 days, ADR-0019).
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from timeutil import format_utc, require_utc

FETCH_TIMEOUT_SECONDS = 60


class FetchRefused(RuntimeError):
    """The pull did not happen or did not return a usable file."""


@dataclass(frozen=True)
class RawFile:
    """A source file exactly as received, with where and when it came from."""

    body: bytes
    url: str
    fetched_at: datetime


def download(url: str, *, now_utc: datetime, opener: Callable = urllib.request.urlopen) -> RawFile:
    """Download one file, stopping on any status other than 200 or an empty body."""
    now_utc = require_utc(now_utc, "now_utc")
    with opener(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise FetchRefused(f"{url} answered HTTP {response.status}")
        body = response.read()
    if not body:
        raise FetchRefused(f"{url} returned an empty body")
    return RawFile(body=body, url=url, fetched_at=now_utc)


def write_raw(client, bucket: str, key: str, manifest_key: str, raw: RawFile) -> dict:  # noqa: ANN001
    """Write the file unchanged and its manifest, and return the manifest.

    ``client`` is a boto3 S3 client.
    """
    manifest = {
        "source_url": raw.url,
        "fetched_at_utc": format_utc(raw.fetched_at),
        "content_sha256": hashlib.sha256(raw.body).hexdigest(),
        "size_bytes": len(raw.body),
        "raw_key": key,
    }
    client.put_object(
        Bucket=bucket, Key=key, Body=raw.body, IfNoneMatch="*", ContentType="application/json"
    )
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode(),
        IfNoneMatch="*",
        ContentType="application/json",
    )
    return manifest


def latest_manifest(client, bucket: str, prefix: str) -> dict | None:  # noqa: ANN001
    """Return the newest manifest under ``prefix``, or None if nothing was pulled yet.

    Every pull's folder is named ``fetched_at=<UTC time>``, which sorts in time order, so the
    newest manifest has the largest key. ``client`` is a boto3 S3 client.
    """
    keys = [
        item["Key"]
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for item in page.get("Contents", [])
        if item["Key"].endswith("manifest.json")
    ]
    if not keys:
        return None
    return json.loads(read_raw(client, bucket, max(keys)))


def read_raw(client, bucket: str, key: str) -> bytes:  # noqa: ANN001
    """Return a raw file exactly as it was kept. ``client`` is a boto3 S3 client."""
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()
