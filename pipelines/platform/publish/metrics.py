"""Run metrics: one row per task run (docs/platform/contracts/platform_run_metrics.yaml).

Each run writes one new Parquet file under its own partition folder. A rerun
of the same task writes the same key again, and readers keep the newest row
per (run_id, dag_id, task_id). Nothing is appended to an existing file.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from timeutil import require_utc

ALLOWED_STATUSES = ("success", "failed", "skipped", "limit_exceeded")

_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("dag_id", pa.string()),
        ("task_id", pa.string()),
        ("project", pa.string()),
        ("data_interval_start_utc", pa.timestamp("us", tz="UTC")),
        ("data_interval_end_utc", pa.timestamp("us", tz="UTC")),
        ("freshest_event_time_utc", pa.timestamp("us", tz="UTC")),
        ("rows_read", pa.int64()),
        ("rows_written", pa.int64()),
        ("status", pa.string()),
        ("emitted_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass(frozen=True)
class RunMetric:
    """Counts and times for one task run."""

    run_id: str
    dag_id: str
    task_id: str
    project: str
    data_interval_start_utc: datetime
    data_interval_end_utc: datetime
    rows_read: int
    rows_written: int
    status: str
    emitted_at_utc: datetime
    freshest_event_time_utc: datetime | None = None

    def __post_init__(self) -> None:
        """Check the values that the contract requires before anything is written."""
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {ALLOWED_STATUSES}, got {self.status!r}")
        if self.rows_read < 0 or self.rows_written < 0:
            raise ValueError("row counts cannot be negative")
        require_utc(self.data_interval_start_utc, "data_interval_start_utc")
        require_utc(self.data_interval_end_utc, "data_interval_end_utc")
        require_utc(self.emitted_at_utc, "emitted_at_utc")


def write_run_metric(metric: RunMetric, table_dir: Path) -> Path:
    """Write one metric row to a new file in its own partition folder and return the path."""
    partition = table_dir / f"dag_id={metric.dag_id}" / f"run_id={metric.run_id}"
    partition.mkdir(parents=True, exist_ok=True)
    row = asdict(metric)
    table = pa.Table.from_pylist([row], schema=_SCHEMA)
    target = partition / f"{metric.task_id}-{uuid.uuid4().hex[:8]}.parquet"
    pq.write_table(table, target, compression="zstd")
    return target
