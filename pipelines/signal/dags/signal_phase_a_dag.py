"""Phase A nightly DAG: satellites (C1, C8, C2), trails (C3, C4) and windows (C5), design doc 8.1.

The orbit steps run in order: pull CelesTrak (or reuse a pull from the last 2 hours), check the
file against its contract, load ``celestrak_gp``, then select the Direct-to-Cell satellites.
The trail step does not need the orbits, so it runs beside them, and loads only when the NPS
pages changed (ADR 0028). The terrain horizons (C4) follow the trails and are computed only for
trail points that have none yet. The satellite windows (C5) wait for both the selected satellites
and the horizons, and cover 26 hours from the run's scheduled time (ADR 0019). The dbt marts (C7)
wait for the windows and the coverage flags. A task that fails
tries twice more, then records an incident and
sends an email, the same as the skeleton.

The DAG only wires tasks together. The logic lives in pipelines/signal/signal_nightly.py.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import alerts
import sample_flow
import signal_nightly
from airflow.sdk import dag, task
from dbt_runner import run_dbt
from incidents import record_failure
from sample_iceberg_job import build_spark_session
from timeutil import require_utc

WAREHOUSE = os.environ.get("PLATFORM_WAREHOUSE", "/data/warehouse")
USE_GLUE = os.environ.get("PLATFORM_USE_GLUE") == "1"
ICEBERG_NAMESPACE = os.environ.get("PLATFORM_ICEBERG_NAMESPACE", "platform")
INCIDENTS_DIR = Path(os.environ.get("PLATFORM_INCIDENTS_DIR", "/data/incidents"))
MARTS_DIR = Path(os.environ.get("PLATFORM_MARTS_DIR", "/data/marts"))


def aws_client(service: str):  # noqa: ANN201
    """Return a boto3 client. The Airflow image provides boto3. Tests replace this function."""
    import boto3

    return boto3.client(service)


def record_failure_callback(context: dict) -> None:
    """File an incident in the lake for a task that failed, then email about it.

    The email goes out even when the incident cannot be filed. The settings are read when the
    callback runs, so a test can point them somewhere else.
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


def _contracts_dir() -> Path:
    return Path(os.environ["SIGNAL_CONTRACTS_DIR"])


def _run_date(dag_run, data_interval_end: datetime | None):  # noqa: ANN001, ANN202
    return sample_flow.run_end(data_interval_end, dag_run.run_after).date()


@dag(
    dag_id="signal_phase_a_nightly",
    schedule="0 10 * * *",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["signal"],
    default_args={
        "on_failure_callback": record_failure_callback,
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
)
def signal_phase_a_nightly():
    """Nightly run of the Phase A satellite and trail steps at 10:00 UTC."""

    @task
    def pull_orbits() -> dict:
        """Pull CelesTrak, or reuse a pull from the last 2 hours; return its manifest."""
        return signal_nightly.pull_orbits(
            aws_client("s3"), os.environ["PLATFORM_RAW_BUCKET"], now_utc=datetime.now(UTC)
        )

    @task
    def check_orbit_schema(manifest: dict) -> int:
        """Stop before loading if the CelesTrak file no longer matches its contract."""
        return signal_nightly.check_orbit_schema(
            aws_client("s3"), os.environ["PLATFORM_RAW_BUCKET"], manifest, _contracts_dir()
        )

    @task
    def load_orbits(
        manifest: dict,
        dag_run=None,  # noqa: ANN001
        data_interval_end: datetime | None = None,
    ) -> int:
        """Write celestrak_gp for the run date."""
        spark = build_spark_session("signal_load_orbits", WAREHOUSE, use_glue=USE_GLUE)
        try:
            return signal_nightly.load_orbits(
                spark,
                aws_client("s3"),
                os.environ["PLATFORM_RAW_BUCKET"],
                manifest,
                _run_date(dag_run, data_interval_end),
                contracts_dir=_contracts_dir(),
                namespace=ICEBERG_NAMESPACE,
            )
        finally:
            spark.stop()

    @task
    def select_dtc(
        manifest: dict,
        dag_run=None,  # noqa: ANN001
        data_interval_end: datetime | None = None,
    ) -> dict:
        """Write dtc_satellite and dtc_disagreement for the run date."""
        spark = build_spark_session("signal_select_dtc", WAREHOUSE, use_glue=USE_GLUE)
        try:
            return signal_nightly.select_and_load_dtc(
                spark,
                aws_client("s3"),
                os.environ["PLATFORM_RAW_BUCKET"],
                manifest,
                _run_date(dag_run, data_interval_end),
                contracts_dir=_contracts_dir(),
                namespace=ICEBERG_NAMESPACE,
            )
        finally:
            spark.stop()

    @task
    def load_trails(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Pull the NPS trails and load them if the pages changed since the last load."""
        spark = build_spark_session("signal_load_trails", WAREHOUSE, use_glue=USE_GLUE)
        try:
            return signal_nightly.load_trails_if_changed(
                spark,
                aws_client("s3"),
                os.environ["PLATFORM_RAW_BUCKET"],
                _run_date(dag_run, data_interval_end),
                contracts_dir=_contracts_dir(),
                namespace=ICEBERG_NAMESPACE,
                now_utc=datetime.now(UTC),
            )
        finally:
            spark.stop()

    @task
    def compute_horizons(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Give the newest trail points their terrain horizons, unless they already have them."""
        spark = build_spark_session("signal_compute_horizons", WAREHOUSE, use_glue=USE_GLUE)
        try:
            # The four GLO-30 tiles (about 155 MB) are needed only while the step runs.
            with tempfile.TemporaryDirectory(prefix="glo30-") as work_dir:
                return signal_nightly.compute_horizons_if_needed(
                    spark,
                    aws_client("s3"),
                    os.environ["PLATFORM_RAW_BUCKET"],
                    _run_date(dag_run, data_interval_end),
                    contracts_dir=_contracts_dir(),
                    namespace=ICEBERG_NAMESPACE,
                    now_utc=datetime.now(UTC),
                    work_dir=Path(work_dir),
                )
        finally:
            spark.stop()

    @task
    def load_coverage(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Load the kept FCC file and flag each trail point, if either changed."""
        spark = build_spark_session("signal_load_coverage", WAREHOUSE, use_glue=USE_GLUE)
        try:
            # The unzipped file (about 290 MB) is needed only while the step runs.
            with tempfile.TemporaryDirectory(prefix="fcc-") as work_dir:
                return signal_nightly.load_coverage_if_changed(
                    spark,
                    aws_client("s3"),
                    os.environ["PLATFORM_RAW_BUCKET"],
                    _run_date(dag_run, data_interval_end),
                    contracts_dir=_contracts_dir(),
                    namespace=ICEBERG_NAMESPACE,
                    now_utc=datetime.now(UTC),
                    work_dir=Path(work_dir),
                )
        finally:
            spark.stop()

    @task
    def compute_windows(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Write the satellite windows for the next 26 hours from the run's scheduled time."""
        spark = build_spark_session("signal_compute_windows", WAREHOUSE, use_glue=USE_GLUE)
        try:
            return signal_nightly.compute_windows(
                spark,
                _run_date(dag_run, data_interval_end),
                contracts_dir=_contracts_dir(),
                namespace=ICEBERG_NAMESPACE,
                span_start_utc=sample_flow.run_end(data_interval_end, dag_run.run_after),
                run_started_utc=require_utc(dag_run.start_date, "start_date"),
                now_utc=datetime.now(UTC),
            )
        finally:
            spark.stop()

    @task
    def build_marts(dag_run=None, data_interval_end: datetime | None = None) -> dict:  # noqa: ANN001
        """Copy tonight's tables to Parquet, then build and test the dbt marts (C7)."""
        spark = build_spark_session("signal_build_marts", WAREHOUSE, use_glue=USE_GLUE)
        with tempfile.TemporaryDirectory(prefix="dbt-") as folder:
            work_dir = Path(folder)
            try:
                copied = signal_nightly.copy_tables_for_dbt(
                    spark,
                    _run_date(dag_run, data_interval_end),
                    namespace=ICEBERG_NAMESPACE,
                    input_dir=work_dir / "input",
                )
            finally:
                spark.stop()
            run_dbt(
                dbt_bin=Path(os.environ["SIGNAL_DBT_BIN"]),
                project_dir=Path(os.environ["SIGNAL_DBT_PROJECT_DIR"]),
                input_dir=work_dir / "input",
                output_dir=MARTS_DIR,
                work_dir=work_dir / "work",
                loaded_at_utc=datetime.now(UTC),
            )
        return copied

    manifest = pull_orbits()
    checked = check_orbit_schema(manifest)
    loaded = load_orbits(manifest)
    checked >> loaded
    selected = select_dtc(manifest)
    loaded >> selected
    horizons = compute_horizons()
    trails = load_trails()
    coverage = load_coverage()
    trails >> [horizons, coverage]
    windows = compute_windows()
    [selected, horizons] >> windows
    [windows, coverage] >> build_marts()


signal_phase_a_nightly()
