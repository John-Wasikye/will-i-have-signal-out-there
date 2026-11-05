"""Publish gate (C9) and publisher (C10) for the trail marts.

The gate checks the finished dbt marts as files, on top of the tests dbt already ran. A failed
check raises ``PublishRefused``, so the task fails, an incident is filed, and the files already
live stay live: the page keeps showing them with its late notice (ADR 0006, QR-4). The limits are
John's, from the measured sizes (OQ-15).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from gate import GateResult, check_not_empty, check_row_limit, evaluate
from metrics import RunMetric, write_run_metric
from publish import publish_tables
from satellite_windows import MAX_WINDOW_ROWS
from timeutil import require_utc
from uploads import upload_tree

MART_NAMES = (
    "dim_trail_point",
    "dim_time",
    "fct_trail_point_coverage",
    "fct_satellite_window",
    "fct_reachable_period",
)
# The decided main trails (ADR 0020). The trail page must answer for each one (AC-1A.6).
MAIN_TRAILS = ("grca-bright-angel", "grca-north-kaibab", "grca-south-kaibab")
FRESHNESS_TARGET_HOURS = 26
MIN_ELEVATION_RANGE_DEG = (0.0, 90.0)
DAG_ID = "signal_phase_a_nightly"
PROJECT = "signal"


def read_marts(marts_dir: Path) -> dict[str, pa.Table]:
    """Read every mart dbt wrote. A missing file raises ``FileNotFoundError``."""
    return {name: pq.read_table(Path(marts_dir) / f"{name}.parquet") for name in MART_NAMES}


def _distinct(table: pa.Table, column: str) -> set:
    return set(pc.unique(table[column]).to_pylist())


def _trail_checks(tables: dict[str, pa.Table]) -> list[str | None]:
    """Check that each main trail has points and windows, and each point has a coverage flag."""
    points = tables["dim_trail_point"]
    trail_of = dict(
        zip(points["trail_point_id"].to_pylist(), points["trail_id"].to_pylist(), strict=True)
    )
    with_windows = {
        trail_of.get(point) for point in _distinct(tables["fct_satellite_window"], "trail_point_id")
    }
    checks: list[str | None] = []
    for trail in MAIN_TRAILS:
        checks.append(None if trail in trail_of.values() else f"{trail}: no trail points")
        checks.append(None if trail in with_windows else f"{trail}: no satellite windows")
    unflagged = len(set(trail_of) - _distinct(tables["fct_trail_point_coverage"], "trail_point_id"))
    checks.append(f"{unflagged} trail points have no coverage flag" if unflagged else None)
    return checks


def _window_checks(windows: pa.Table, now_utc: datetime) -> list[str | None]:
    """Check the windows' freshness, minimum elevation and order."""
    if windows.num_rows == 0:
        return []
    checks: list[str | None] = []
    newest = pc.max(windows["run_started_utc"]).as_py()
    if now_utc - newest > timedelta(hours=FRESHNESS_TARGET_HOURS):
        checks.append(f"the run started at {newest}, older than {FRESHNESS_TARGET_HOURS} hours")
    low, high = MIN_ELEVATION_RANGE_DEG
    angles = pc.min_max(windows["min_elevation_deg"]).as_py()
    if angles["min"] < low or angles["max"] > high:
        checks.append(f"min_elevation_deg is outside {low} to {high}: {angles}")
    backwards = pc.sum(pc.greater(windows["window_start_utc"], windows["window_end_utc"])).as_py()
    if backwards:
        checks.append(f"{backwards} windows end before they start")
    return checks


def gate_marts(tables: dict[str, pa.Table], now_utc: datetime) -> GateResult:
    """Run every check on the marts and combine the results."""
    now_utc = require_utc(now_utc, "now_utc")
    windows = tables["fct_satellite_window"]
    return evaluate(
        [
            *(check_not_empty(name, table.num_rows) for name, table in tables.items()),
            check_row_limit("fct_satellite_window", windows.num_rows, MAX_WINDOW_ROWS),
            *_trail_checks(tables),
            *_window_checks(windows, now_utc),
        ]
    )


def publish_marts(marts_dir: Path, published_dir: Path, now_utc: datetime) -> dict:
    """Gate the marts and write them to ``published_dir``, or raise ``PublishRefused``."""
    tables = read_marts(marts_dir)
    published = publish_tables(tables, gate_marts(tables, now_utc), published_dir)
    windows = tables["fct_satellite_window"]
    return {
        "tables": len(published),
        "windows": windows.num_rows,
        "points": tables["dim_trail_point"].num_rows,
        "run_started_utc": pc.max(windows["run_started_utc"]).as_py().isoformat(),
    }


def emit_publish_metric(
    summary: dict, run_end_utc: datetime, now_utc: datetime, metrics_dir: Path
) -> Path:
    """Write the run's freshness and row count to the metrics table (FR-24)."""
    run_end_utc = require_utc(run_end_utc, "run_end_utc")
    return write_run_metric(
        RunMetric(
            run_id=f"{run_end_utc:%Y%m%dT%H%M%SZ}",
            dag_id=DAG_ID,
            task_id="publish_marts",
            project=PROJECT,
            data_interval_start_utc=run_end_utc - timedelta(hours=24),
            data_interval_end_utc=run_end_utc,
            rows_read=summary["windows"],
            rows_written=summary["windows"],
            status="success",
            emitted_at_utc=require_utc(now_utc, "now_utc"),
            freshest_event_time_utc=datetime.fromisoformat(summary["run_started_utc"]),
        ),
        metrics_dir,
    )


def upload_published(
    client,  # noqa: ANN001, a boto3 S3 client
    site_bucket: str,
    lake_bucket: str,
    published_dir: Path,
    metrics_dir: Path,
) -> list[str]:
    """Copy the marts to where the API reads them, and the metrics to the lake."""
    return [
        *upload_tree(client, site_bucket, "published/", published_dir),
        *upload_tree(client, lake_bucket, "platform/run_metrics/", metrics_dir),
    ]
