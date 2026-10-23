"""Skeleton flow: sample rows -> gate -> publish -> run metric -> status.

The flow is split into three tasks so the DAG can run each one on its own:
publish_sample, emit_sample_metric and publish_sample_status. The Spark job
(pipelines/platform/spark) writes the same rows to Iceberg before this flow publishes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
from gate import check_not_empty, check_row_limit, evaluate
from metrics import RunMetric, write_run_metric
from publish import publish_tables
from sample_rows import FRESHNESS_TARGET_HOURS, build_sample_rows
from status import PipelineStatus, write_status
from timeutil import require_utc

PIPELINE_NAME = "platform_skeleton"
DAG_ID = "platform_skeleton_nightly"
PROJECT = "platform"
MAX_ROWS = 1_000

SAMPLE_TABLE_NAME = "sample_answer"


@dataclass(frozen=True)
class PublishOutcome:
    """Result of publish_sample, passed to the metric and status tasks."""

    passed: bool
    row_count: int
    published: tuple[Path, ...] = ()


def outcome_to_dict(outcome: PublishOutcome) -> dict:
    """Turn an outcome into plain values that Airflow can pass between tasks."""
    return {
        "passed": outcome.passed,
        "row_count": outcome.row_count,
        "published": [str(path) for path in outcome.published],
    }


def outcome_from_dict(values: dict) -> PublishOutcome:
    """Rebuild an outcome from the dict made by outcome_to_dict."""
    return PublishOutcome(
        passed=values["passed"],
        row_count=values["row_count"],
        published=tuple(Path(path) for path in values["published"]),
    )


def build_sample_table(now_utc: datetime) -> pa.Table:
    """Return the published table: the sample rows without the partition column."""
    rows = build_sample_rows(now_utc, run_date=require_utc(now_utc, "now_utc").date())
    return pa.table(
        {
            "key": [row["key"] for row in rows],
            "value": [row["value"] for row in rows],
            "last_good_run_utc": pa.array(
                [row["last_good_run_utc"] for row in rows], pa.timestamp("us", "UTC")
            ),
            "freshness_target_hours": pa.array(
                [row["freshness_target_hours"] for row in rows], pa.float64()
            ),
        }
    )


def publish_sample(now_utc: datetime, published_dir: Path) -> PublishOutcome:
    """Run the gate and publish the sample table only if the gate passes."""
    table = build_sample_table(require_utc(now_utc, "now_utc"))
    gate = evaluate(
        [
            check_not_empty(SAMPLE_TABLE_NAME, table.num_rows),
            check_row_limit(SAMPLE_TABLE_NAME, table.num_rows, MAX_ROWS),
        ]
    )
    if not gate.passed:
        return PublishOutcome(passed=False, row_count=table.num_rows)

    published = publish_tables({SAMPLE_TABLE_NAME: table}, gate, published_dir)
    return PublishOutcome(passed=True, row_count=table.num_rows, published=tuple(published))


def emit_sample_metric(now_utc: datetime, outcome: PublishOutcome, metrics_dir: Path) -> Path:
    """Write one run metric row for the publish task and return its file path."""
    now_utc = require_utc(now_utc, "now_utc")
    return write_run_metric(
        RunMetric(
            run_id=f"{now_utc:%Y%m%dT%H%M%SZ}",
            dag_id=DAG_ID,
            task_id="publish_sample",
            project=PROJECT,
            data_interval_start_utc=now_utc - timedelta(hours=24),
            data_interval_end_utc=now_utc,
            rows_read=outcome.row_count,
            rows_written=outcome.row_count if outcome.passed else 0,
            status="success" if outcome.passed else "failed",
            emitted_at_utc=now_utc,
            freshest_event_time_utc=now_utc if outcome.passed else None,
        ),
        metrics_dir,
    )


def publish_sample_status(now_utc: datetime, outcome: PublishOutcome, status_path: Path) -> dict:
    """Write status.json so the status page shows this run, and return the document."""
    now_utc = require_utc(now_utc, "now_utc")
    return write_status(
        [
            PipelineStatus(
                name=PIPELINE_NAME,
                freshness_target_hours=FRESHNESS_TARGET_HOURS,
                last_good_run_utc=now_utc if outcome.passed else None,
                last_row_count=outcome.row_count if outcome.passed else None,
                last_run_failed=not outcome.passed,
            )
        ],
        now_utc,
        status_path,
    )
