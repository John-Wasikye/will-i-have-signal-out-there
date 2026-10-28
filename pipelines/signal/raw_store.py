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
