"""Skeleton nightly DAG: publish the sample with its metrics, status and Iceberg maintenance.

The sample is written to Iceberg first, then published. Once the outputs are in S3, the run
is reported: an email for a late or failed pipeline, or a CloudWatch data point for a good
one. Iceberg maintenance runs last. A task that fails tries twice more, then records an
incident and sends an email.

Order follows docs/platform/design-doc.md section 7.4. The DAG only wires tasks together.
The logic lives in modules that have their own tests:
- pipelines/platform/publish/sample_flow.py
- pipelines/platform/publish/alerts.py
- pipelines/platform/publish/incidents.py
- pipelines/platform/publish/uploads.py
- pipelines/platform/spark/sample_iceberg_job.py
- pipelines/platform/spark/iceberg_maintenance.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import alerts
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
ICEBERG_NAMESPACE = os.environ.get("PLATFORM_ICEBERG_NAMESPACE", "platform")
ICEBERG_TABLE = "sample_answer"
MAX_SPARK_ROWS = 1_000


def aws_client(service: str):  # noqa: ANN201
    """Return a boto3 client. The Airflow image provides boto3. Tests replace this function."""
    import boto3

    return boto3.client(service)


def record_failure_callback(context: dict) -> None:
    """File an incident in the lake for a task that failed, then email about it.

    Airflow calls this with the task's context. The email goes out even when the incident
    cannot be filed, and the filing error is raised afterwards so Airflow logs it. The settings
    are read when the callback runs, so a test can point them somewhere else.
    """
    try:
        record_failure(
            context,
            Path(os.environ.get("PLATFORM_INCIDENTS_DIR", str(INCIDENTS_DIR))),
            aws_client("s3"),
            os.environ["PLATFORM_LAKE_BUCKET"],
        )
    finally:
        alerts.alert_failure(
            context,
            aws_client("sns"),
            os.environ["PLATFORM_ALERT_TOPIC_ARN"],
            os.environ["PLATFORM_ENV"],
        )


@dag(
    dag_id="platform_skeleton_nightly",
    schedule="0 10 * * *",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["platform"],
    # Two tries more for a brief failure, such as a task that starts before the API server is
    # up at boot. Every task overwrites its own output, so a retry is safe. The incident and the
    # email come only after the last try fails.
    default_args={
        "on_failure_callback": record_failure_callback,
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
)
def platform_skeleton_nightly():
    """Nightly run of the skeleton. The schedule is 10:00 UTC (design doc section 2)."""

    @task
    def write_iceberg_sample(dag_run=None, data_interval_end: datetime | None = None) -> None:  # noqa: ANN001
        """Overwrite today's partition of the sample Iceberg table."""
        end = sample_flow.run_end(data_interval_end, dag_run.run_after)
        spark = build_spark_session("platform_skeleton", WAREHOUSE, use_glue=USE_GLUE)
        try:
            run_sample_iceberg_job(
                spark,
                ICEBERG_TABLE,
                run_date=end.date(),
                now_utc=end,
                namespace=ICEBERG_NAMESPACE,
                max_rows=MAX_SPARK_ROWS,
            )
        finally:
            spark.stop()

    @task
    def publish_sample(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Run the publish gate and publish the sample Parquet file."""
        end = sample_flow.run_end(data_interval_end, dag_run.run_after)
        outcome = sample_flow.publish_sample(end, PUBLISHED_DIR)
        return sample_flow.outcome_to_dict(outcome)

    @task
    def emit_metrics(
        outcome: dict,
        dag_run=None,  # noqa: ANN001
        data_interval_end: datetime | None = None,
    ) -> str:
        """Write the run metric row and return its file path."""
        end = sample_flow.run_end(data_interval_end, dag_run.run_after)
        path = sample_flow.emit_sample_metric(
            end, sample_flow.outcome_from_dict(outcome), METRICS_DIR
        )
        return str(path)

    @task
    def publish_status(
        outcome: dict,
        dag_run=None,  # noqa: ANN001
        data_interval_end: datetime | None = None,
    ) -> dict:
        """Write status.json for the status page."""
        end = sample_flow.run_end(data_interval_end, dag_run.run_after)
        return sample_flow.publish_sample_status(
            end,
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

    @task
    def report_run(status: dict) -> None:
        """Email about a late or failed pipeline, or record a good run in CloudWatch.

        It runs after the upload, so a good run is recorded only once its data is live.
        """
        alerts.report_status(
            aws_client("sns"),
            aws_client("cloudwatch"),
            os.environ["PLATFORM_ALERT_TOPIC_ARN"],
            status,
            os.environ["PLATFORM_ENV"],
            datetime.now(UTC),
        )

    @task(trigger_rule="all_done")
    def iceberg_maintenance() -> None:
        """Compact, expire and clean up Iceberg tables. Runs even when earlier tasks fail."""
        spark = build_spark_session("platform_skeleton_maintenance", WAREHOUSE, use_glue=USE_GLUE)
        try:
            maintain_tables(spark, [ICEBERG_TABLE], datetime.now(UTC), namespace=ICEBERG_NAMESPACE)
        finally:
            spark.stop()

    written = write_iceberg_sample()
    outcome = publish_sample()
    written >> outcome
    metrics = emit_metrics(outcome)
    status = publish_status(outcome)
    uploaded = upload_outputs()
    [metrics, status] >> uploaded
    uploaded >> report_run(status)
    maintenance = iceberg_maintenance()
    uploaded >> maintenance


platform_skeleton_nightly()
