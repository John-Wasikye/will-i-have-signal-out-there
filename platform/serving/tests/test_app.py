"""Serving API tests: /health and /sample against published Parquet."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

import app as serving_app


def _write_sample(path: Path, last_good: datetime, target_hours: float = 26.0) -> None:
    table = pa.table(
        {
            "key": ["b-row", "a-row"],
            "value": ["second", "first"],
            "last_good_run_utc": pa.array([last_good, last_good], pa.timestamp("us", "UTC")),
            "freshness_target_hours": pa.array([target_hours, target_hours], pa.float64()),
        }
    )
    pq.write_table(table, path)


@pytest.fixture
def published(tmp_path, monkeypatch):
    """Point the app at a temporary published file made just now."""
    sample = tmp_path / "sample_answer.parquet"
    _write_sample(sample, datetime.now(UTC))
    monkeypatch.setattr(serving_app, "SAMPLE_TABLE", sample)
    return sample


@pytest.fixture
def client(published):
    return TestClient(serving_app.app)


def test_health_is_ok_when_published_data_can_be_read(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_is_500_when_published_data_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(serving_app, "SAMPLE_TABLE", tmp_path / "missing.parquet")
    response = TestClient(serving_app.app).get("/health")
    assert response.status_code == 500


def test_sample_without_key_returns_first_row_by_key(client):
    response = client.get("/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "a-row"
    assert body["value"] == "first"
    assert body["late"] is False


def test_sample_with_key_returns_that_row(client):
    response = client.get("/sample", params={"key": "b-row"})
    assert response.status_code == 200
    assert response.json()["value"] == "second"


def test_sample_unknown_key_is_404(client):
    response = client.get("/sample", params={"key": "nope"})
    assert response.status_code == 404
    assert response.json()["detail"] == "No sample row with that key."


def test_sample_key_longer_than_64_characters_is_rejected(client):
    response = client.get("/sample", params={"key": "x" * 65})
    assert response.status_code == 422


def test_sample_marks_old_data_late_but_still_returns_it(published, client):
    _write_sample(published, datetime.now(UTC) - timedelta(hours=30))
    response = client.get("/sample", params={"key": "a-row"})
    assert response.status_code == 200
    body = response.json()
    assert body["late"] is True
    assert body["value"] == "first"
