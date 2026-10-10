"""Structure tests for the skeleton Airflow DAG.

Airflow does not install on Windows, so these tests skip locally and run where Airflow is
installed (CI, or the session box). The rules come from docs/platform/design-doc.md:
- the Iceberg sample is written before it is published
- metrics and status come after publishing
- iceberg_maintenance runs last, and runs even when earlier tasks fail
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
        "iceberg_maintenance",
    }


def test_publish_waits_for_the_iceberg_write(skeleton_dag):
    publish = skeleton_dag.get_task("publish_sample")
    assert "write_iceberg_sample" in publish.upstream_task_ids


def test_metrics_and_status_wait_for_publishing(skeleton_dag):
    for task_id in ("emit_metrics", "publish_status"):
        assert "publish_sample" in skeleton_dag.get_task(task_id).upstream_task_ids


def test_maintenance_waits_for_metrics_and_status(skeleton_dag):
    maintenance = skeleton_dag.get_task("iceberg_maintenance")
    assert {"emit_metrics", "publish_status"} <= set(maintenance.upstream_task_ids)


def test_maintenance_runs_even_when_earlier_tasks_fail(skeleton_dag):
    maintenance = skeleton_dag.get_task("iceberg_maintenance")
    assert maintenance.trigger_rule == "all_done"
