"""End to end: the skeleton flow publishes, writes status, and the serving API reads it."""

import json
from datetime import UTC, datetime

import pyarrow.parquet as pq
import sample_flow
from fastapi.testclient import TestClient
from sample_flow import run_sample_flow

import app as serving_app

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def test_flow_publishes_sample_table_and_status_ok(tmp_path):
    published = run_sample_flow(
        NOW, tmp_path / "published", tmp_path / "status.json", tmp_path / "metrics"
    )

    assert published == [tmp_path / "published" / "sample_answer.parquet"]
    assert pq.read_table(published[0]).num_rows == 3

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    pipeline = status["pipelines"][0]
    assert pipeline["name"] == "platform_skeleton"
    assert pipeline["state"] == "ok"
    assert pipeline["last_row_count"] == 3
    assert pipeline["last_good_run_utc"] == "2026-10-09T10:00:00Z"

    metric_files = list((tmp_path / "metrics").rglob("*.parquet"))
    assert len(metric_files) == 1
    metric_rows = pq.ParquetFile(metric_files[0]).read()
    assert metric_rows.column("status").to_pylist() == ["success"]


def test_failed_gate_publishes_nothing_and_status_shows_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(sample_flow, "MAX_ROWS", 0)
    published_dir = tmp_path / "published"

    published = run_sample_flow(NOW, published_dir, tmp_path / "status.json", tmp_path / "metrics")

    assert published == []
    assert not (published_dir / "sample_answer.parquet").exists()
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["pipelines"][0]["state"] == "failed"
    assert "last_good_run_utc" not in status["pipelines"][0]


def test_serving_api_reads_what_the_flow_published(tmp_path, monkeypatch):
    published_dir = tmp_path / "published"
    run_sample_flow(
        datetime.now(UTC), published_dir, tmp_path / "status.json", tmp_path / "metrics"
    )
    monkeypatch.setattr(serving_app, "SAMPLE_TABLE", published_dir / "sample_answer.parquet")

    client = TestClient(serving_app.app)
    response = client.get("/sample", params={"key": "iceberg"})

    assert response.status_code == 200
    assert response.json()["value"] == "This row went through Spark and Iceberg."
    assert response.json()["late"] is False
