"""Tests for the run alerts (ADR-0024, PR-14).

A failed task, or a run that leaves a pipeline late or failed, sends one email through an
SNS topic. A good run instead records one data point in CloudWatch, so an alarm can email me
when no good run has been seen for longer than the freshness target, for example when the
box never started.
"""

from datetime import UTC, datetime

import pytest
from alerts import (
    MAX_SUBJECT_LENGTH,
    METRIC_NAME,
    METRIC_NAMESPACE,
    Alert,
    alert_failure,
    failure_alert,
    record_good_runs,
    report_status,
    send_alert,
    status_alert,
    stop_alert,
)

TOPIC = "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"
NOW = datetime(2026, 10, 10, 10, 30, tzinfo=UTC)


class FakeSns:
    def __init__(self):
        self.published = []

    def publish(self, **kwargs):
        self.published.append(kwargs)
        return {"MessageId": "fake-message-id"}


class FakeCloudWatch:
    def __init__(self):
        self.metric_calls = []

    def put_metric_data(self, **kwargs):
        self.metric_calls.append(kwargs)


def status_document(*pipelines):
    return {"generated_at_utc": "2026-10-10T10:30:00Z", "pipelines": list(pipelines)}


def pipeline(name, state):
    return {"name": name, "state": state, "freshness_target_hours": 26.0}


# --- Failed tasks ---------------------------------------------------------------------------


def test_a_failed_task_alert_names_the_dag_the_task_and_the_error():
    alert = failure_alert("platform_skeleton_nightly", "publish_sample", "disk full", "dev")

    assert "publish_sample" in alert.subject
    assert "platform_skeleton_nightly" in alert.message
    assert "publish_sample" in alert.message
    assert "disk full" in alert.message


def test_the_subject_says_which_environment_the_alert_came_from():
    assert failure_alert("d", "t", "x", "live").subject.startswith("[live]")


def test_a_very_long_error_is_cut_so_the_email_stays_short():
    alert = failure_alert("d", "t", "x" * 5000, "dev")

    assert len(alert.message) < 1000


def test_an_alert_refuses_an_unknown_environment():
    with pytest.raises(ValueError, match="dev or live"):
        failure_alert("d", "t", "x", "staging")


# --- Status after a run ---------------------------------------------------------------------


def test_no_alert_when_every_pipeline_is_ok():
    document = status_document(pipeline("platform_skeleton", "ok"))

    assert status_alert(document, "dev") is None


def test_a_late_or_failed_pipeline_gets_an_alert_that_names_it_and_its_state():
    document = status_document(
        pipeline("platform_skeleton", "failed"),
        pipeline("orbits", "late"),
        pipeline("trails", "ok"),
    )

    alert = status_alert(document, "live")

    assert alert is not None
    assert "platform_skeleton: failed" in alert.message
    assert "orbits: late" in alert.message
    assert "trails" not in alert.message
    assert alert.subject.startswith("[live]")


# --- Sending --------------------------------------------------------------------------------


def test_an_alert_is_published_to_the_topic():
    sns = FakeSns()

    send_alert(sns, TOPIC, Alert(subject="Run failed", message="Details."))

    assert sns.published == [{"TopicArn": TOPIC, "Subject": "Run failed", "Message": "Details."}]


def test_a_long_subject_is_cut_to_the_sns_limit():
    sns = FakeSns()

    send_alert(sns, TOPIC, Alert(subject="s" * 500, message="x"))

    assert len(sns.published[0]["Subject"]) == MAX_SUBJECT_LENGTH


def test_a_subject_with_a_line_break_is_made_one_line():
    sns = FakeSns()

    send_alert(sns, TOPIC, Alert(subject="first\nsecond", message="x"))

    assert sns.published[0]["Subject"] == "first second"


def test_sending_refuses_a_topic_that_is_not_an_sns_arn():
    with pytest.raises(ValueError, match="SNS topic ARN"):
        send_alert(FakeSns(), "portfolio-dev-run-alerts", Alert(subject="s", message="m"))


# --- Good runs ------------------------------------------------------------------------------


def test_a_good_run_records_one_data_point_per_ok_pipeline():
    cloudwatch = FakeCloudWatch()
    document = status_document(pipeline("platform_skeleton", "ok"), pipeline("orbits", "late"))

    record_good_runs(cloudwatch, document, "dev", NOW)

    assert len(cloudwatch.metric_calls) == 1
    call = cloudwatch.metric_calls[0]
    assert call["Namespace"] == METRIC_NAMESPACE
    assert call["MetricData"] == [
        {
            "MetricName": METRIC_NAME,
            "Dimensions": [
                {"Name": "Environment", "Value": "dev"},
                {"Name": "Pipeline", "Value": "platform_skeleton"},
            ],
            "Timestamp": NOW,
            "Value": 1.0,
            "Unit": "Count",
        }
    ]


def test_no_data_point_when_no_pipeline_is_ok():
    cloudwatch = FakeCloudWatch()

    record_good_runs(cloudwatch, status_document(pipeline("p", "failed")), "dev", NOW)

    assert cloudwatch.metric_calls == []


def test_recording_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        record_good_runs(FakeCloudWatch(), status_document(), "dev", datetime(2026, 10, 10))


# --- Reporting a finished run ---------------------------------------------------------------


def test_reporting_a_good_run_records_it_and_sends_no_email():
    sns, cloudwatch = FakeSns(), FakeCloudWatch()

    report_status(sns, cloudwatch, TOPIC, status_document(pipeline("p", "ok")), "dev", NOW)

    assert sns.published == []
    assert len(cloudwatch.metric_calls) == 1


def test_reporting_a_failed_run_sends_one_email():
    sns, cloudwatch = FakeSns(), FakeCloudWatch()

    report_status(sns, cloudwatch, TOPIC, status_document(pipeline("p", "failed")), "dev", NOW)

    assert len(sns.published) == 1
    assert cloudwatch.metric_calls == []


# --- Airflow's failure callback -------------------------------------------------------------


def test_the_failure_callback_emails_about_the_task_in_the_airflow_context():
    sns = FakeSns()
    context = {
        "dag": type("Dag", (), {"dag_id": "platform_skeleton_nightly"})(),
        "task_instance": type("TaskInstance", (), {"task_id": "publish_sample"})(),
        "exception": RuntimeError("disk full"),
    }

    alert_failure(context, sns, TOPIC, "dev")

    assert len(sns.published) == 1
    assert "publish_sample" in sns.published[0]["Subject"]
    assert "disk full" in sns.published[0]["Message"]


# --- The watchdog stopping a nightly run ----------------------------------------------------


def test_a_stopped_nightly_run_gets_an_alert_with_the_reason():
    alert = stop_alert("The nightly run reached its 2 hour maximum.", "live")

    assert alert.subject.startswith("[live]")
    assert "stopped" in alert.subject
    assert "2 hour maximum" in alert.message
