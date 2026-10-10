"""Tests for incident records (docs/platform/contracts/platform_incidents.yaml).

An incident is a short record of something that really broke: what broke, when, and where.
The cause and the fix are filled in later, by hand. Free text must hold no key or address.
"""

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from incidents import build_incident, failure_incident, record_failure, write_incident

OPENED = datetime(2026, 10, 10, 10, 30, tzinfo=UTC)


def test_an_incident_has_the_contract_fields():
    incident = build_incident(
        number=3,
        opened_utc=OPENED,
        pipeline="platform_skeleton_nightly",
        what_broke="Something broke.",
    )

    assert incident == {
        "incident_id": "INC-2026-10-10-03",
        "opened_at_utc": "2026-10-10T10:30:00Z",
        "project": "platform",
        "pipeline": "platform_skeleton_nightly",
        "what_broke": "Something broke.",
        "reached_maximum_runtime": False,
        "status": "open",
    }


def test_an_incident_can_say_the_run_reached_its_maximum():
    incident = build_incident(
        number=1,
        opened_utc=OPENED,
        pipeline="p",
        what_broke="Too slow.",
        reached_maximum_runtime=True,
    )

    assert incident["reached_maximum_runtime"] is True


def test_an_incident_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_incident(1, datetime(2026, 10, 10, 10, 30), "p", "x")


def test_an_incident_refuses_a_number_below_one():
    with pytest.raises(ValueError, match="at least 1"):
        build_incident(0, OPENED, "p", "x")


def test_a_failed_task_becomes_an_incident_that_names_the_dag_and_the_task():
    incident = failure_incident(
        number=1,
        opened_utc=OPENED,
        dag_id="platform_skeleton_nightly",
        task_id="publish_sample",
        error="ValueError: bad row",
    )

    assert incident["pipeline"] == "platform_skeleton_nightly"
    assert "publish_sample" in incident["what_broke"]
    assert "ValueError: bad row" in incident["what_broke"]
    assert incident["reached_maximum_runtime"] is False


def test_a_very_long_error_is_cut_so_the_record_stays_short():
    incident = failure_incident(1, OPENED, "d", "t", error="x" * 5000)

    assert len(incident["what_broke"]) < 500


def test_an_incident_is_written_as_a_parquet_file_with_the_contract_columns(tmp_path):
    incident = build_incident(1, OPENED, "p", "Something broke.")

    path = write_incident(incident, tmp_path)

    table = pq.ParquetFile(path).read()
    assert set(table.column_names) == {
        "incident_id",
        "opened_at_utc",
        "closed_at_utc",
        "project",
        "pipeline",
        "what_broke",
        "cause",
        "fix",
        "github_issue_url",
        "reached_maximum_runtime",
        "status",
    }
    row = table.to_pylist()[0]
    assert row["incident_id"] == "INC-2026-10-10-01"
    assert row["status"] == "open"
    assert row["closed_at_utc"] is None
    assert row["cause"] is None


def test_writing_the_same_incident_twice_replaces_the_file(tmp_path):
    incident = build_incident(1, OPENED, "p", "Something broke.")

    first = write_incident(incident, tmp_path)
    second = write_incident(incident, tmp_path)

    assert first == second
    assert len(list(tmp_path.rglob("*.parquet"))) == 1


class FakeTaskInstance:
    def __init__(self, task_id: str):
        self.task_id = task_id


def test_the_failure_callback_records_an_incident_from_the_airflow_context(tmp_path):
    context = {
        "dag": type("Dag", (), {"dag_id": "platform_skeleton_nightly"})(),
        "task_instance": FakeTaskInstance("publish_sample"),
        "exception": RuntimeError("disk full"),
    }

    path = record_failure(context, tmp_path, now_utc=OPENED)

    row = pq.ParquetFile(path).read().to_pylist()[0]
    assert row["pipeline"] == "platform_skeleton_nightly"
    assert "publish_sample" in row["what_broke"]
    assert "disk full" in row["what_broke"]
    assert row["incident_id"] == "INC-2026-10-10-01"


def test_a_second_failure_on_the_same_day_gets_the_next_number(tmp_path):
    context = {
        "dag": type("Dag", (), {"dag_id": "d"})(),
        "task_instance": FakeTaskInstance("t"),
        "exception": RuntimeError("x"),
    }

    record_failure(context, tmp_path, now_utc=OPENED)
    second = record_failure(context, tmp_path, now_utc=OPENED)

    assert pq.ParquetFile(second).read().to_pylist()[0]["incident_id"] == "INC-2026-10-10-02"
