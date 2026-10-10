"""Skeleton nightly DAG: publish the sample with its metrics, status and Iceberg maintenance.

The sample is written to Iceberg first, then published. Iceberg maintenance runs last.

Order follows docs/platform/design-doc.md section 7.4. The DAG only wires tasks together.
The logic lives in modules that have their own tests:
- pipelines/platform/publish/sample_flow.py
- pipelines/platform/publish/incidents.py
- pipelines/platform/publish/uploads.py
- pipelines/platform/spark/sample_iceberg_job.py
- pipelines/platform/spark/iceberg_maintenance.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import sample_flow
import uploads
from airflow.sdk import dag, task
from iceberg_maintenance import maintain_tables
from incidents import record_failure
from sample_iceberg_job import build_spark_session, run_sample_iceberg_job

PUBLISHED_DIR = Path(os.environ.get("PLATFORM_PUBLISHED_DIR", "/data/published"))
METRICS_DIR = Path(os.environ.get("PLATFORM_METRICS_DIR", "/data/metrics"))
INCIDENTS_DIR = Path(os.environ.get("PLATFORM_INCIDENTS_DIR", "/data/incidents"))
WAREHOUSE = os.environ.get("PLATFORM_WAREHOUSE", "/data/warehouse")
USE_GLUE = os.environ.get("PLATFORM_USE_GLUE") == "1"
ICEBERG_TABLE = "sample_answer"
MAX_SPARK_ROWS = 1_000


def record_failure_callback(context: dict) -> None:
    """Record an incident for a task that failed. Airflow calls this with the task's context.

    The folder is read when the callback runs, so a test can point it somewhere else.
    """
    record_failure(context, Path(os.environ.get("PLATFORM_INCIDENTS_DIR", str(INCIDENTS_DIR))))


@dag(
    dag_id="platform_skeleton_nightly",
    schedule="0 10 * * *",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    tags=["platform"],
    default_args={"on_failure_callback": record_failure_callback},
)
def platform_skeleton_nightly():
    """Nightly run of the skeleton. The schedule is 10:00 UTC (design doc section 2)."""

    @task
    def write_iceberg_sample(data_interval_end: datetime) -> None:
        """Overwrite today's partition of the sample Iceberg table."""
        spark = build_spark_session("platform_skeleton", WAREHOUSE, use_glue=USE_GLUE)
        try:
            run_sample_iceberg_job(
                spark,
                ICEBERG_TABLE,
                run_date=data_interval_end.date(),
                now_utc=data_interval_end,
                max_rows=MAX_SPARK_ROWS,
            )
        finally:
            spark.stop()

    @task
    def publish_sample(data_interval_end: datetime) -> dict:
        """Run the publish gate and publish the sample Parquet file."""
        outcome = sample_flow.publish_sample(data_interval_end, PUBLISHED_DIR)
        return sample_flow.outcome_to_dict(outcome)

    @task
    def emit_metrics(outcome: dict, data_interval_end: datetime) -> str:
        """Write the run metric row and return its file path."""
        path = sample_flow.emit_sample_metric(
            data_interval_end, sample_flow.outcome_from_dict(outcome), METRICS_DIR
        )
        return str(path)

    @task
    def publish_status(outcome: dict, data_interval_end: datetime) -> dict:
        """Write status.json for the status page."""
        return sample_flow.publish_sample_status(
            data_interval_end,
            sample_flow.outcome_from_dict(outcome),
            PUBLISHED_DIR / "status.json",
        )

    @task
    def upload_outputs() -> list[str]:
        """Copy the published files, status.json, metrics and incidents to S3.

        The box is switched off most of the time, so nothing is live until this runs.
        """
        import boto3  # The Airflow image provides boto3.

        locations = uploads.OutputLocations(
            site_bucket=os.environ["PLATFORM_SITE_BUCKET"],
            lake_bucket=os.environ["PLATFORM_LAKE_BUCKET"],
        )
        return uploads.upload_outputs(
            boto3.client("s3"), locations, PUBLISHED_DIR, METRICS_DIR, INCIDENTS_DIR
        )

    @task(trigger_rule="all_done")
    def iceberg_maintenance() -> None:
        """Compact, expire and clean up Iceberg tables. Runs even when earlier tasks fail."""
        spark = build_spark_session("platform_skeleton_maintenance", WAREHOUSE, use_glue=USE_GLUE)
        try:
            maintain_tables(spark, [ICEBERG_TABLE], datetime.now(UTC))
        finally:
            spark.stop()

    written = write_iceberg_sample()
    outcome = publish_sample()
    written >> outcome
    metrics = emit_metrics(outcome)
    status = publish_status(outcome)
    uploaded = upload_outputs()
    [metrics, status] >> uploaded
    maintenance = iceberg_maintenance()
    uploaded >> maintenance


platform_skeleton_nightly()
