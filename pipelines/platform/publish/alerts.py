"""Run alerts by email, through an SNS topic (ADR-0024, PR-14).

Two things send an email:
- a task that fails (Airflow's failure callback)
- a finished run whose status.json shows a pipeline as late or failed. The publish gate can
  refuse a run without any task failing, so the failure callback alone would miss it.

A good run records one data point in CloudWatch instead. An alarm in the alerts Terraform
module emails me when no data point arrives within the freshness target, which catches a box
that never started. Nothing on the box can report that case itself.

The email can hold a short error text that names files or tables. It goes to me only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from timeutil import require_utc

# SNS refuses an email subject longer than 100 characters.
MAX_SUBJECT_LENGTH = 100
MAX_ERROR_LENGTH = 300

METRIC_NAMESPACE = "Portfolio/Platform"
METRIC_NAME = "GoodRunPublished"

_ENVIRONMENTS = ("dev", "live")


@dataclass(frozen=True)
class Alert:
    """One email: a one-line subject and a plain-text message."""

    subject: str
    message: str


def _require_environment(env: str) -> str:
    if env not in _ENVIRONMENTS:
        raise ValueError(f"env must be dev or live, got {env!r}")
    return env


def failure_alert(dag_id: str, task_id: str, error: str, env: str) -> Alert:
    """Build the alert for a task that failed. The error text is cut to a short length."""
    _require_environment(env)
    if len(error) > MAX_ERROR_LENGTH:
        error = error[: MAX_ERROR_LENGTH - 3] + "..."
    return Alert(
        subject=f"[{env}] Task {task_id} failed",
        message=(
            f"Task {task_id} in {dag_id} failed in the {env} environment.\n\n"
            f"Error: {error}\n\n"
            "An incident record was written to the lake."
        ),
    )


def alert_failure(context: Mapping, client, topic_arn: str, env: str) -> None:  # noqa: ANN001
    """Airflow's failure callback: email about the task that failed.

    ``context`` is the dictionary Airflow passes to a callback. ``client`` is a boto3 SNS client.
    """
    alert = failure_alert(
        dag_id=context["dag"].dag_id,
        task_id=context["task_instance"].task_id,
        error=str(context.get("exception", "no error was reported")),
        env=env,
    )
    send_alert(client, topic_arn, alert)


def stop_alert(reason: str, env: str) -> Alert:
    """Build the alert for a nightly run the box watchdog stopped before it finished.

    The box powers off, so no task fails and the run never reports. The watchdog sends this.
    """
    _require_environment(env)
    return Alert(
        subject=f"[{env}] The nightly run was stopped before it finished",
        message=(
            f"The box watchdog stopped the nightly run in the {env} environment.\n\n"
            f"Reason: {reason}\n\n"
            "An incident record was written to the lake. The next nightly run catches up."
        ),
    )


def unplanned_start_alert(reason: str, env: str) -> Alert:
    """Build the alert for a boot that was neither the nightly run nor a work session I planned.

    AWS restarts a spot box by itself once capacity comes back, at any hour. The watchdog stops
    it at once and sends this, so I know the box ran when it should not have.
    """
    _require_environment(env)
    return Alert(
        subject=f"[{env}] The session box started when nobody planned it",
        message=(
            f"The box watchdog stopped the session box in the {env} environment.\n\n"
            f"Reason: {reason}\n\n"
            "No pipeline run was stopped. If this happens often, look at the spot capacity."
        ),
    )


def status_alert(status: Mapping, env: str) -> Alert | None:
    """Build the alert for a status.json document, or return None when every pipeline is ok."""
    _require_environment(env)
    problems = [p for p in status["pipelines"] if p["state"] != "ok"]
    if not problems:
        return None
    lines = "\n".join(f"- {p['name']}: {p['state']}" for p in problems)
    return Alert(
        subject=f"[{env}] {len(problems)} pipeline(s) late or failed",
        message=(
            f"The run at {status['generated_at_utc']} left these pipelines late or failed "
            f"in the {env} environment:\n\n{lines}\n\n"
            "The status page shows the same."
        ),
    )


def send_alert(client, topic_arn: str, alert: Alert) -> None:  # noqa: ANN001
    """Publish one alert to the SNS topic. ``client`` is a boto3 SNS client."""
    if not topic_arn.startswith("arn:") or ":sns:" not in topic_arn:
        raise ValueError(f"topic_arn must be an SNS topic ARN, got {topic_arn!r}")
    subject = " ".join(alert.subject.split())[:MAX_SUBJECT_LENGTH]
    client.publish(TopicArn=topic_arn, Subject=subject, Message=alert.message)


def record_good_runs(client, status: Mapping, env: str, now_utc: datetime) -> None:  # noqa: ANN001
    """Record one data point for each pipeline that is ok. ``client`` is a CloudWatch client."""
    _require_environment(env)
    now = require_utc(now_utc, "now_utc")
    data = [
        {
            "MetricName": METRIC_NAME,
            "Dimensions": [
                {"Name": "Environment", "Value": env},
                {"Name": "Pipeline", "Value": p["name"]},
            ],
            "Timestamp": now,
            "Value": 1.0,
            "Unit": "Count",
        }
        for p in status["pipelines"]
        if p["state"] == "ok"
    ]
    if data:
        client.put_metric_data(Namespace=METRIC_NAMESPACE, MetricData=data)


def report_status(
    sns,  # noqa: ANN001
    cloudwatch,  # noqa: ANN001
    topic_arn: str,
    status: Mapping,
    env: str,
    now_utc: datetime,
) -> None:
    """Report a finished run: record the good pipelines, and email about the others."""
    record_good_runs(cloudwatch, status, env, now_utc)
    alert = status_alert(status, env)
    if alert is not None:
        send_alert(sns, topic_arn, alert)
