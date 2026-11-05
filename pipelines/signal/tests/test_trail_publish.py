"""Tests for the publish gate (C9) and the publisher (C10) of the trail marts.

The gate reads the finished dbt marts. A failed check stops the task, so the files already live
stay live and the page shows them with its late notice (ADR 0006, QR-4). No test calls AWS.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from publish import PublishRefused
from trail_publish import (
    MAIN_TRAILS,
    emit_publish_metric,
    gate_marts,
    publish_marts,
    read_marts,
    upload_published,
)

NOW = datetime(2026, 11, 5, 10, 30, tzinfo=UTC)
RUN_STARTED = datetime(2026, 11, 5, 10, 1, tzinfo=UTC)
RUN_END = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
UTC_US = pa.timestamp("us", tz="UTC")
SCHEMA = pa.schema(
    [
        ("trail_point_id", pa.string()),
        ("window_start_utc", UTC_US),
        ("window_end_utc", UTC_US),
        ("min_elevation_deg", pa.float64()),
        ("run_logical_date", pa.date32()),
        ("run_started_utc", UTC_US),
    ]
)


def _point(trail: str) -> str:
    return f"{trail}-00000"


def _window(trail: str = MAIN_TRAILS[0], **changes) -> dict:
    return {
        "trail_point_id": _point(trail),
        "window_start_utc": RUN_END,
        "window_end_utc": RUN_END + timedelta(minutes=3),
        "min_elevation_deg": 10.0,
        "run_logical_date": date(2026, 11, 5),
        "run_started_utc": RUN_STARTED,
        **changes,
    }


def _tables(windows=None, points=MAIN_TRAILS, coverage=MAIN_TRAILS) -> dict[str, pa.Table]:
    rows = [_window(trail) for trail in MAIN_TRAILS] if windows is None else windows
    return {
        "dim_trail_point": pa.Table.from_pylist(
            [{"trail_point_id": _point(trail), "trail_id": trail} for trail in points]
        ),
        "dim_time": pa.Table.from_pylist([{"time_key": "20261105T1000Z", "time_utc": RUN_END}]),
        "fct_trail_point_coverage": pa.Table.from_pylist(
            [{"trail_point_id": _point(trail), "covered": True} for trail in coverage]
        ),
        "fct_satellite_window": pa.Table.from_pylist(rows, schema=SCHEMA),
    }


def _failures(tables: dict[str, pa.Table], now: datetime = NOW) -> str:
    return "; ".join(gate_marts(tables, now).failures)


def _write(tables: dict[str, pa.Table], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        pq.write_table(table, folder / f"{name}.parquet")
    return folder


def test_the_main_trails_are_the_three_decided_trails():
    assert set(MAIN_TRAILS) == {"grca-bright-angel", "grca-north-kaibab", "grca-south-kaibab"}


def test_good_marts_pass_the_gate():
    assert gate_marts(_tables(), NOW).passed


def test_an_empty_mart_fails_the_gate():
    tables = _tables()
    tables["dim_time"] = tables["dim_time"].slice(0, 0)
    assert "dim_time: no rows" in _failures(tables)


def test_too_many_windows_fail_the_gate(monkeypatch):
    monkeypatch.setattr("trail_publish.MAX_WINDOW_ROWS", 2)
    assert "over the limit of 2" in _failures(_tables())


def test_a_main_trail_with_no_points_fails_the_gate():
    assert f"{MAIN_TRAILS[1]}: no trail points" in _failures(_tables(points=MAIN_TRAILS[::2]))


def test_a_main_trail_with_no_windows_fails_the_gate():
    windows = [_window(MAIN_TRAILS[0]), _window(MAIN_TRAILS[2])]
    assert f"{MAIN_TRAILS[1]}: no satellite windows" in _failures(_tables(windows))


def test_a_trail_point_with_no_coverage_flag_fails_the_gate():
    message = "1 trail points have no coverage flag"
    assert message in _failures(_tables(coverage=MAIN_TRAILS[:2]))


def test_a_run_older_than_26_hours_fails_the_gate():
    assert "older than 26 hours" in _failures(
        _tables(), RUN_STARTED + timedelta(hours=26, minutes=1)
    )


def test_a_run_exactly_26_hours_old_passes_the_gate():
    assert gate_marts(_tables(), RUN_STARTED + timedelta(hours=26)).passed


@pytest.mark.parametrize("angle", [-0.1, 90.1])
def test_a_minimum_elevation_outside_0_to_90_degrees_fails_the_gate(angle):
    rows = [_window(trail, min_elevation_deg=angle) for trail in MAIN_TRAILS]
    assert "min_elevation_deg" in _failures(_tables(rows))


def test_a_window_that_ends_before_it_starts_fails_the_gate():
    backwards = _window(window_end_utc=RUN_END - timedelta(minutes=1))
    rows = [backwards, *[_window(trail) for trail in MAIN_TRAILS[1:]]]
    assert "1 windows end before they start" in _failures(_tables(rows))


def test_a_missing_mart_file_stops_the_read(tmp_path):
    tables = _tables()
    del tables["dim_time"]
    with pytest.raises(FileNotFoundError):
        read_marts(_write(tables, tmp_path))


def test_good_marts_are_published_with_their_times_unchanged(tmp_path):
    marts = _write(_tables(), tmp_path / "marts")
    summary = publish_marts(marts, tmp_path / "published", NOW)
    names = {path.name for path in (tmp_path / "published").iterdir()}
    assert names == {
        "dim_trail_point.parquet",
        "dim_time.parquet",
        "fct_trail_point_coverage.parquet",
        "fct_satellite_window.parquet",
    }
    table = pq.read_table(tmp_path / "published" / "fct_satellite_window.parquet")
    assert table.schema.field("window_start_utc").type == UTC_US
    assert table.to_pylist()[0]["window_start_utc"] == RUN_END
    assert summary == {
        "tables": 4,
        "windows": 3,
        "points": 3,
        "run_started_utc": RUN_STARTED.isoformat(),
    }


def test_a_failed_gate_publishes_nothing_and_keeps_the_last_files(tmp_path):
    published = tmp_path / "published"
    published.mkdir()
    (published / "fct_satellite_window.parquet").write_text("last good", encoding="utf-8")
    marts = _write(_tables(windows=[_window()]), tmp_path / "marts")
    with pytest.raises(PublishRefused, match="no satellite windows"):
        publish_marts(marts, published, NOW)
    assert (published / "fct_satellite_window.parquet").read_text(encoding="utf-8") == "last good"
    assert [path.name for path in published.iterdir()] == ["fct_satellite_window.parquet"]


def test_the_run_metric_records_the_rows_and_the_freshest_time(tmp_path):
    summary = {"tables": 4, "windows": 3, "points": 3, "run_started_utc": RUN_STARTED.isoformat()}
    path = emit_publish_metric(summary, RUN_END, NOW, tmp_path)
    (row,) = pq.read_table(path).to_pylist()
    assert path.parent.parent.name == "dag_id=signal_phase_a_nightly"
    assert path.parent.name == "run_id=20261105T100000Z"
    assert row["task_id"] == "publish_marts"
    assert row["rows_written"] == 3
    assert row["status"] == "success"
    assert row["freshest_event_time_utc"] == RUN_STARTED


class FakeS3:
    """Keeps the bucket and key of each upload."""

    def __init__(self):
        self.keys: list[tuple[str, str]] = []

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):  # noqa: N803, boto3 names
        self.keys.append((Bucket, Key))


def test_the_marts_go_to_the_folder_the_api_reads_and_the_metrics_to_the_lake(tmp_path):
    published, metrics = tmp_path / "published", tmp_path / "metrics"
    published.mkdir()
    (published / "fct_satellite_window.parquet").write_text("x", encoding="utf-8")
    metric = metrics / "dag_id=d" / "run_id=r"
    metric.mkdir(parents=True)
    (metric / "m.parquet").write_text("x", encoding="utf-8")
    client = FakeS3()
    upload_published(client, "site", "lake", published, metrics)
    assert client.keys == [
        ("site", "published/fct_satellite_window.parquet"),
        ("lake", "platform/run_metrics/dag_id=d/run_id=r/m.parquet"),
    ]
