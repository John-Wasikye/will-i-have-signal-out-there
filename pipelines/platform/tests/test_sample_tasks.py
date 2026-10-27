"""Tests for the three separate tasks of the skeleton flow, as the DAG runs them."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import sample_flow
from sample_flow import (
    PublishOutcome,
    emit_sample_metric,
    outcome_from_dict,
    outcome_to_dict,
    publish_sample,
    publish_sample_status,
)

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def test_outcome_survives_a_round_trip_through_a_json_safe_dict():
    outcome = PublishOutcome(
        passed=True,
        row_count=3,
        published=(Path("published/sample_answer.parquet"),),
    )

    as_dict = outcome_to_dict(outcome)

    assert json.loads(json.dumps(as_dict)) == as_dict
    assert outcome_from_dict(as_dict) == outcome


def test_publish_task_reports_a_passing_outcome_with_its_files(tmp_path):
    outcome = publish_sample(NOW, tmp_path / "published")

    assert outcome.passed is True
    assert outcome.row_count == 3
    assert outcome.published == (tmp_path / "published" / "sample_answer.parquet",)
    assert pq.read_table(outcome.published[0]).num_rows == 3


def test_publish_task_reports_a_failed_gate_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(sample_flow, "MAX_ROWS", 0)

    outcome = publish_sample(NOW, tmp_path / "published")

    assert outcome.passed is False
    assert outcome.published == ()
    assert not (tmp_path / "published" / "sample_answer.parquet").exists()


def test_metric_task_writes_success_for_a_passing_outcome(tmp_path):
    outcome = publish_sample(NOW, tmp_path / "published")

    path = emit_sample_metric(NOW, outcome, tmp_path / "metrics")

    assert pq.ParquetFile(path).read().column("status").to_pylist() == ["success"]


def test_metric_task_writes_failed_for_a_failed_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(sample_flow, "MAX_ROWS", 0)
    outcome = publish_sample(NOW, tmp_path / "published")

    path = emit_sample_metric(NOW, outcome, tmp_path / "metrics")

    assert pq.ParquetFile(path).read().column("status").to_pylist() == ["failed"]


def test_status_task_marks_the_pipeline_ok_after_a_pass(tmp_path):
    outcome = publish_sample(NOW, tmp_path / "published")

    document = publish_sample_status(NOW, outcome, tmp_path / "status.json")

    assert document["pipelines"][0]["state"] == "ok"
    assert json.loads((tmp_path / "status.json").read_text(encoding="utf-8")) == document


def test_a_scheduled_run_ends_at_its_data_interval_end():
    run_after = datetime(2026, 10, 9, 10, 5, tzinfo=UTC)

    assert sample_flow.run_end(NOW, run_after) == NOW


def test_a_run_started_by_hand_ends_when_it_was_started():
    run_after = datetime(2026, 10, 9, 16, 38, tzinfo=UTC)

    assert sample_flow.run_end(None, run_after) == run_after
