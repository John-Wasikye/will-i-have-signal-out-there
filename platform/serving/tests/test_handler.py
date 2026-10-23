"""Tests for the Lambda entry point: refresh the published files, then answer the request."""

from datetime import UTC, datetime

import handler as lambda_entry
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import app as serving_app


def _health_event() -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/health",
                "sourceIp": "127.0.0.1",
                "protocol": "HTTP/1.1",
            },
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


class RecordingCache:
    def __init__(self):
        self.refresh_times: list[datetime] = []

    def refresh_if_stale(self, now: datetime) -> None:
        self.refresh_times.append(now)


@pytest.fixture
def published_sample(tmp_path, monkeypatch):
    path = tmp_path / "sample_answer.parquet"
    now = datetime.now(UTC)
    pq.write_table(
        pa.table(
            {
                "key": ["a"],
                "value": ["v"],
                "last_good_run_utc": pa.array([now], pa.timestamp("us", "UTC")),
                "freshness_target_hours": pa.array([26.0], pa.float64()),
            }
        ),
        path,
    )
    monkeypatch.setattr(serving_app, "SAMPLE_TABLE", path)


def test_a_request_refreshes_the_published_files_before_it_is_answered(
    published_sample, monkeypatch
):
    cache = RecordingCache()
    monkeypatch.setattr(lambda_entry, "_cache", cache)

    response = lambda_entry.handler(_health_event(), None)

    assert len(cache.refresh_times) == 1
    assert cache.refresh_times[0].tzinfo == UTC
    assert response["statusCode"] == 200


def test_without_a_bucket_the_handler_answers_from_local_files(published_sample, monkeypatch):
    monkeypatch.setattr(lambda_entry, "_cache", None)

    response = lambda_entry.handler(_health_event(), None)

    assert response["statusCode"] == 200


def test_no_cache_is_built_when_no_bucket_is_set(monkeypatch):
    monkeypatch.delenv("PUBLISHED_BUCKET", raising=False)

    assert lambda_entry.build_cache() is None
