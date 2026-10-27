"""Structure tests for the skeleton Airflow DAG.

Airflow does not install on Windows, so these tests skip locally and run where Airflow is
installed (CI, or the session box). The rules come from docs/platform/design-doc.md:
- the Iceberg sample is written before it is published
- metrics and status come after publishing
- iceberg_maintenance runs last, and runs even when earlier tasks fail
- report_run emails about a late or failed pipeline once the outputs are in S3
- a failed task records an incident and sends an email
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


def test_every_task_records_an_incident_when_it_fails(skeleton_dag):
    module = importlib.import_module("platform_skeleton_dag")

    assert skeleton_dag.default_args["on_failure_callback"] is module.record_failure_callback


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


@pytest.fixture
def failure_context():
    return {
        "dag": type("Dag", (), {"dag_id": "platform_skeleton_nightly"})(),
        "task_instance": type("TaskInstance", (), {"task_id": "publish_sample"})(),
        "exception": RuntimeError("disk full"),
    }


@pytest.fixture
def fake_sns(monkeypatch, tmp_path):
    """Point the callback at a temporary folder, a fake topic and a fake SNS client."""
    module = importlib.import_module("platform_skeleton_dag")
    sns = FakeSns()
    monkeypatch.setenv("PLATFORM_INCIDENTS_DIR", str(tmp_path))
    monkeypatch.setenv("PLATFORM_ENV", "dev")
    monkeypatch.setenv(
        "PLATFORM_ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"
    )
    monkeypatch.setattr(module, "aws_client", lambda service: sns)
    return sns


def test_the_failure_callback_writes_an_incident_file(fake_sns, failure_context, tmp_path):
    module = importlib.import_module("platform_skeleton_dag")

    module.record_failure_callback(failure_context)

    assert len(list(tmp_path.glob("INC-*.parquet"))) == 1


def test_the_failure_callback_sends_one_email(fake_sns, failure_context):
    module = importlib.import_module("platform_skeleton_dag")

    module.record_failure_callback(failure_context)

    assert len(fake_sns.published) == 1
    assert "publish_sample" in fake_sns.published[0]["Subject"]


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
