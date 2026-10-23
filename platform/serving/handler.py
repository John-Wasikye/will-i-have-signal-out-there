"""AWS Lambda entry point for the serving template.

API Gateway (HTTP type) invokes this handler. Before it answers, the handler makes sure
the local copy of the published files is fresh. Then Mangum passes the request to the
FastAPI app in app.py.

Locally there is no PUBLISHED_BUCKET, so no copying happens and the app reads its own
PUBLISHED_DIR folder.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from mangum import Mangum
from published_files import PublishedFilesCache

import app as serving_app

SYNC_TTL_SECONDS = 300


def build_cache() -> PublishedFilesCache | None:
    """Build the cache from the function's settings, or None when no bucket is set."""
    bucket = os.environ.get("PUBLISHED_BUCKET")
    if not bucket:
        return None

    import boto3  # The Lambda runtime provides boto3, so it is not in the package.

    return PublishedFilesCache(
        client=boto3.client("s3"),
        bucket=bucket,
        prefix=os.environ.get("PUBLISHED_PREFIX", "published/"),
        target_dir=serving_app.PUBLISHED_DIR,
        ttl_seconds=SYNC_TTL_SECONDS,
    )


_cache = build_cache()
_asgi_handler = Mangum(serving_app.app, lifespan="off")


def handler(event: dict, context: object) -> dict:
    """Refresh the published files if they are stale, then answer the request."""
    if _cache is not None:
        _cache.refresh_if_stale(datetime.now(UTC))
    return _asgi_handler(event, context)
