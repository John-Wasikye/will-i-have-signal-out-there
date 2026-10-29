"""Structure tests for the Phase A nightly DAG (design doc 8.1).

Airflow does not install on Windows, so these tests skip locally and run where Airflow is
installed (CI, or the Airflow image). The rules:
- C1 pulls, C8 checks the file, then C1 loads it and C2 selects from it, in that order
- C3 does not wait for the orbit steps
- every task tries twice more, then records an incident and sends an email
- only one run is active at a time, and a fresh install starts the DAG unpaused
- Airflow reads exactly the two DAG files under pipelines/, nothing else there
"""

import importlib
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("airflow.sdk", reason="Airflow is not installed here")

PIPELINES = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def signal_dag():
    module = importlib.import_module("signal_phase_a_dag")
    return module.signal_phase_a_nightly()


def test_the_dag_runs_every_night_at_ten_utc(signal_dag):
    assert signal_dag.dag_id == "signal_phase_a_nightly"
    assert signal_dag.timetable.expression == "0 10 * * *"


def test_only_one_run_is_active_at_a_time(signal_dag):
    assert signal_dag.max_active_runs == 1


def test_a_fresh_install_does_not_leave_the_dag_paused(signal_dag):
    assert signal_dag.is_paused_upon_creation is False


def test_every_step_is_a_task(signal_dag):
    assert {task.task_id for task in signal_dag.tasks} == {
        "pull_orbits",
        "check_orbit_schema",
        "load_orbits",
        "select_dtc",
        "load_trails",
    }


def test_the_orbit_steps_run_in_order(signal_dag):
    assert signal_dag.get_task("check_orbit_schema").upstream_task_ids == {"pull_orbits"}
    assert signal_dag.get_task("load_orbits").upstream_task_ids == {
        "pull_orbits",
        "check_orbit_schema",
    }
    assert "load_orbits" in signal_dag.get_task("select_dtc").upstream_task_ids


def test_the_trails_do_not_wait_for_the_orbits(signal_dag):
    assert signal_dag.get_task("load_trails").upstream_task_ids == set()


def test_a_task_tries_again_after_a_brief_failure(signal_dag):
    for task in signal_dag.tasks:
        assert task.retries == 2, task.task_id
        assert task.retry_delay == timedelta(minutes=2), task.task_id


def test_every_task_records_an_incident_when_it_fails(signal_dag):
    module = importlib.import_module("signal_phase_a_dag")

    assert signal_dag.default_args["on_failure_callback"] is module.record_failure_callback


def test_every_task_runs_without_a_data_interval(signal_dag):
    """Airflow 3 leaves data_interval_end out of the context of a run started by hand."""
    import inspect

    for task in signal_dag.tasks:
        required = [
            name
            for name, parameter in inspect.signature(task.python_callable).parameters.items()
            if parameter.default is inspect.Parameter.empty and name.startswith("data_interval")
        ]
        assert required == [], task.task_id


def test_airflow_reads_only_the_dag_files_under_pipelines():
    from airflow.utils.file import list_py_file_paths

    found = {Path(path).relative_to(PIPELINES).as_posix() for path in list_py_file_paths(PIPELINES)}

    assert found == {
        "platform/dags/platform_skeleton_dag.py",
        "signal/dags/signal_phase_a_dag.py",
    }


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)


class FakeLake:
    def __init__(self):
        self.objects = {}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        found = [{"Key": key} for (_, key) in self.objects if key.startswith(Prefix)]
        yield {"Contents": found} if found else {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        self.objects[(Bucket, Key)] = Body


def test_the_failure_callback_files_an_incident_and_sends_one_email(monkeypatch, tmp_path):
    module = importlib.import_module("signal_phase_a_dag")
    clients = {"sns": FakeSns(), "s3": FakeLake()}
    monkeypatch.setenv("PLATFORM_INCIDENTS_DIR", str(tmp_path))
    monkeypatch.setenv("PLATFORM_ENV", "dev")
    monkeypatch.setenv("PLATFORM_LAKE_BUCKET", "lake-bucket")
    monkeypatch.setenv(
        "PLATFORM_ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"
    )
    monkeypatch.setattr(module, "aws_client", lambda service: clients[service])
    context = {
        "dag": type("Dag", (), {"dag_id": "signal_phase_a_nightly"})(),
        "task_instance": type("TaskInstance", (), {"task_id": "pull_orbits"})(),
        "exception": RuntimeError("HTTP 403"),
    }

    module.record_failure_callback(context)

    assert len(clients["s3"].objects) == 1
    assert len(clients["sns"].published) == 1
    assert "pull_orbits" in clients["sns"].published[0]["Subject"]
