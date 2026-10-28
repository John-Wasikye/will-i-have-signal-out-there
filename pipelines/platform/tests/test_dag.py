"""Structure tests for the skeleton Airflow DAG.

Airflow does not install on Windows, so these tests skip locally and run where Airflow is
installed (CI, or the session box). The rules come from docs/platform/design-doc.md:
- the Iceberg sample is written before it is published
- metrics and status come after publishing
- iceberg_maintenance runs last, and runs even when earlier tasks fail
- report_run emails about a late or failed pipeline once the outputs are in S3
- a failed task records an incident and sends an email
- only one run is active at a time, because every run writes the same table
- a fresh install starts the DAG unpaused, so the nightly schedule runs without a manual step
"""

import importlib

import pytest

pytest.importorskip("airflow.sdk", reason="Airflow is not installed here")


@pytest.fixture(scope="module")
def skeleton_dag():
    module = importlib.import_module("platform_skeleton_dag")
    return module.platform_skeleton_nightly()


def test_dag_has_the_platform_skeleton_id(skeleton_dag):
    assert skeleton_dag.dag_id == "platform_skeleton_nightly"


def test_only_one_run_is_active_at_a_time(skeleton_dag):
    """Two runs at once raced to create the Iceberg table on a fresh box (2026-10-27)."""
    assert skeleton_dag.max_active_runs == 1


def test_a_fresh_install_does_not_leave_the_dag_paused(skeleton_dag):
    """Airflow pauses a new DAG by default, so an empty database would skip every night."""
    assert skeleton_dag.is_paused_upon_creation is False


def test_every_task_is_in_the_dag(skeleton_dag):
    task_ids = {task.task_id for task in skeleton_dag.tasks}
    assert task_ids == {
        "write_iceberg_sample",
        "publish_sample",
        "emit_metrics",
        "publish_status",
        "upload_outputs",
        "report_run",
        "iceberg_maintenance",
    }


def test_publish_waits_for_the_iceberg_write(skeleton_dag):
    publish = skeleton_dag.get_task("publish_sample")
    assert "write_iceberg_sample" in publish.upstream_task_ids


def test_metrics_and_status_wait_for_publishing(skeleton_dag):
    for task_id in ("emit_metrics", "publish_status"):
        assert "publish_sample" in skeleton_dag.get_task(task_id).upstream_task_ids


def test_the_upload_waits_for_metrics_and_status(skeleton_dag):
    upload = skeleton_dag.get_task("upload_outputs")
    assert {"emit_metrics", "publish_status"} <= set(upload.upstream_task_ids)


def test_the_run_is_reported_after_the_upload_from_the_status(skeleton_dag):
    report = skeleton_dag.get_task("report_run")
    assert {"upload_outputs", "publish_status"} <= set(report.upstream_task_ids)


def test_maintenance_waits_for_the_upload(skeleton_dag):
    maintenance = skeleton_dag.get_task("iceberg_maintenance")
    assert "upload_outputs" in maintenance.upstream_task_ids


def test_maintenance_runs_even_when_earlier_tasks_fail(skeleton_dag):
    maintenance = skeleton_dag.get_task("iceberg_maintenance")
    assert maintenance.trigger_rule == "all_done"


def test_a_task_tries_again_after_a_brief_failure(skeleton_dag):
    # On 2026-10-28 a task started 8 seconds before the API server and failed for good.
    from datetime import timedelta

    for task in skeleton_dag.tasks:
        assert task.retries == 2, task.task_id
        assert task.retry_delay == timedelta(minutes=2), task.task_id


def test_every_task_records_an_incident_when_it_fails(skeleton_dag):
    module = importlib.import_module("platform_skeleton_dag")

    assert skeleton_dag.default_args["on_failure_callback"] is module.record_failure_callback


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


class FakeLake:
    """Just enough S3 for filing an incident: listing, and put_object with If-None-Match."""

    def __init__(self, broken: bool = False):
        self.objects = {}
        self.broken = broken

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        if self.broken:
            raise ConnectionError("S3 cannot be reached")
        found = [{"Key": key} for key in self.objects if key.startswith(Prefix)]
        yield {"Contents": found} if found else {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        self.objects[(Bucket, Key)] = Body


@pytest.fixture
def failure_context():
    return {
        "dag": type("Dag", (), {"dag_id": "platform_skeleton_nightly"})(),
        "task_instance": type("TaskInstance", (), {"task_id": "publish_sample"})(),
        "exception": RuntimeError("disk full"),
    }


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Point the callback at a temporary folder, a fake topic, and fake SNS and S3 clients."""
    module = importlib.import_module("platform_skeleton_dag")
    clients = {"sns": FakeSns(), "s3": FakeLake()}
    monkeypatch.setenv("PLATFORM_INCIDENTS_DIR", str(tmp_path))
    monkeypatch.setenv("PLATFORM_ENV", "dev")
    monkeypatch.setenv("PLATFORM_LAKE_BUCKET", "lake-bucket")
    monkeypatch.setenv(
        "PLATFORM_ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"
    )
    monkeypatch.setattr(module, "aws_client", lambda service: clients[service])
    return clients


def test_the_failure_callback_files_the_incident_in_the_lake(fakes, failure_context):
    from datetime import UTC, datetime

    module = importlib.import_module("platform_skeleton_dag")

    module.record_failure_callback(failure_context)

    today = datetime.now(UTC)
    assert list(fakes["s3"].objects) == [
        ("lake-bucket", f"platform/incidents/INC-{today:%Y-%m-%d}-01.parquet")
    ]


def test_the_failure_callback_sends_one_email(fakes, failure_context):
    module = importlib.import_module("platform_skeleton_dag")

    module.record_failure_callback(failure_context)

    assert len(fakes["sns"].published) == 1
    assert "publish_sample" in fakes["sns"].published[0]["Subject"]


def test_the_email_is_still_sent_when_the_incident_cannot_be_filed(fakes, failure_context):
    module = importlib.import_module("platform_skeleton_dag")
    fakes["s3"].broken = True

    with pytest.raises(ConnectionError):
        module.record_failure_callback(failure_context)

    assert len(fakes["sns"].published) == 1


def test_every_task_runs_without_a_data_interval(skeleton_dag):
    """Airflow 3 leaves data_interval_end out of the context of a run started by hand."""
    import inspect

    for task in skeleton_dag.tasks:
        required = [
            name
            for name, parameter in inspect.signature(task.python_callable).parameters.items()
            if parameter.default is inspect.Parameter.empty and name.startswith("data_interval")
        ]
        assert required == [], task.task_id
