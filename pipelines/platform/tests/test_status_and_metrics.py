"""Status document, pipeline states and run metric tests."""

import json
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest
from metrics import RunMetric, write_run_metric
from status import PipelineStatus, build_status_document, pipeline_state, write_status

NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def _pipeline(**overrides) -> PipelineStatus:
    values = {"name": "p", "freshness_target_hours": 26.0}
    values.update(overrides)
    return PipelineStatus(**values)


def test_recent_good_run_is_ok():
    pipeline = _pipeline(last_good_run_utc=NOW - timedelta(hours=2))
    assert pipeline_state(pipeline, NOW) == "ok"


def test_run_older_than_target_is_late():
    pipeline = _pipeline(last_good_run_utc=NOW - timedelta(hours=27))
    assert pipeline_state(pipeline, NOW) == "late"


def test_no_good_run_yet_is_late():
    assert pipeline_state(_pipeline(), NOW) == "late"


def test_latest_failed_run_is_failed_even_with_a_recent_good_run():
    pipeline = _pipeline(last_good_run_utc=NOW, last_run_failed=True)
    assert pipeline_state(pipeline, NOW) == "failed"


def test_document_matches_the_contract_keys(tmp_path):
    pipeline = _pipeline(
        last_good_run_utc=NOW,
        last_row_count=3,
        incident_url="https://github.com/John-Wasikye/will-i-have-signal-out-there/issues/1",
    )
    document = build_status_document([pipeline], NOW)
    assert set(document) == {"generated_at_utc", "pipelines"}
    entry = document["pipelines"][0]
    assert entry == {
        "name": "p",
        "state": "ok",
        "freshness_target_hours": 26.0,
        "last_good_run_utc": "2026-10-09T10:00:00Z",
        "last_row_count": 3,
        "incident_url": "https://github.com/John-Wasikye/will-i-have-signal-out-there/issues/1",
    }


def test_document_omits_optional_fields_when_unknown():
    entry = build_status_document([_pipeline()], NOW)["pipelines"][0]
    assert entry["state"] == "late"
    assert "last_good_run_utc" not in entry
    assert "last_row_count" not in entry
    assert "incident_url" not in entry


def test_write_status_creates_the_file_and_returns_the_document(tmp_path):
    path = tmp_path / "status.json"
    written = write_status([_pipeline(last_good_run_utc=NOW)], NOW, path)
    assert json.loads(path.read_text(encoding="utf-8")) == written
    assert not (tmp_path / "status.json.tmp").exists()


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        pipeline_state(_pipeline(), datetime(2026, 10, 9, 10, 0))


def _metric(**overrides) -> RunMetric:
    values = {
        "run_id": "run-1",
        "dag_id": "dag",
        "task_id": "task",
        "project": "platform",
        "data_interval_start_utc": NOW - timedelta(hours=24),
        "data_interval_end_utc": NOW,
        "rows_read": 3,
        "rows_written": 3,
        "status": "success",
        "emitted_at_utc": NOW,
    }
    values.update(overrides)
    return RunMetric(**values)


def test_run_metric_rejects_unknown_status():
    with pytest.raises(ValueError, match="status must be one of"):
        _metric(status="maybe")


def test_run_metric_rejects_negative_counts():
    with pytest.raises(ValueError, match="cannot be negative"):
        _metric(rows_written=-1)


def test_run_metric_rejects_naive_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        _metric(emitted_at_utc=datetime(2026, 10, 9, 10, 0))


def test_run_metric_rejects_a_naive_freshest_event_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        _metric(freshest_event_time_utc=datetime(2026, 10, 9, 9, 0))


def test_run_metric_accepts_no_freshest_event_time():
    assert _metric(freshest_event_time_utc=None).freshest_event_time_utc is None


def test_write_run_metric_writes_one_row_per_partition_file(tmp_path):
    path = write_run_metric(_metric(), tmp_path)
    assert path.parent.name == "run_id=run-1"
    assert path.parent.parent.name == "dag_id=dag"
    # Read the file itself: pyarrow would otherwise treat the dag_id= folder as a partition column.
    table = pq.ParquetFile(path).read()
    assert table.num_rows == 1
    assert table.column("status").to_pylist() == ["success"]
