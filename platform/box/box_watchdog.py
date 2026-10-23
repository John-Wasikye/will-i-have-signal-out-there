"""The box watchdog: decides when the session box should switch itself off.

The box runs the nightly pipelines and then stops, so it only bills while it works. There
are three reasons to stop, and this is their order of priority:

1. AWS is about to take the spot instance back. It sends a notice two minutes ahead.
2. The nightly run has finished, whether it succeeded or failed.
3. The box has been up for the 2-hour nightly maximum.

A box I start by hand is a work session. Only a spot warning or the 4-hour session limit stops
it here; the idle alarm can stop it too.

A run that finished is never called a timeout, even if the watchdog notices it late.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

import airflow_db_backup
import alerts
from incidents import build_incident, write_incident
from nightly_limit import reached_maximum
from timeutil import format_utc, require_utc
from uploads import upload_tree

logger = logging.getLogger(__name__)

METADATA_URL = "http://169.254.169.254"


class RunProgress(Enum):
    """Where the nightly run stands, as far as the watchdog can tell."""

    WAITING = "waiting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Action(Enum):
    """What the watchdog does next."""

    KEEP_WAITING = "keep waiting"
    STOP_FINISHED = "stop: the run finished"
    STOP_MAXIMUM = "stop: the 2 hour maximum"
    STOP_SPOT_WARNING = "stop: AWS is taking the box back"
    STOP_SESSION_LIMIT = "stop: the 4 hour session limit"


# ADR-0013: every box session lasts at most 4 hours. The 14:00 UTC hard stop bounds only the
# nightly run, so the watchdog enforces this for a session I start at any other time.
WORK_SESSION_LIMIT = timedelta(hours=4)


@dataclass(frozen=True)
class Decision:
    """The next action and the reason for it, in words I can put in a log or an incident."""

    action: Action
    reason: str


_RUN_STATES = {
    "queued": RunProgress.RUNNING,
    "running": RunProgress.RUNNING,
    "success": RunProgress.SUCCEEDED,
    "failed": RunProgress.FAILED,
}


def run_progress(runs_json: str, box_started_utc: datetime) -> RunProgress:
    """Read the output of ``airflow dags list-runs --output json`` for the nightly DAG.

    Only runs created after the box started count, because a run from an earlier night says
    nothing about tonight. The newest of those runs decides.
    """
    started = require_utc(box_started_utc, "box_started_utc")
    runs = [
        run for run in json.loads(runs_json) if datetime.fromisoformat(run["run_after"]) >= started
    ]
    if not runs:
        return RunProgress.WAITING

    newest = max(runs, key=lambda run: datetime.fromisoformat(run["run_after"]))
    try:
        return _RUN_STATES[newest["state"]]
    except KeyError:
        raise ValueError(f"unknown run state {newest['state']!r}") from None


def decide(
    now_utc: datetime,
    box_started_utc: datetime,
    progress: RunProgress,
    spot_stop_utc: datetime | None,
    nightly: bool = True,
) -> Decision:
    """Choose the next action. ``spot_stop_utc`` is set only when AWS has sent its notice.

    ``nightly`` is False for a work session that I start by hand. A work session is stopped
    here only by a spot warning or the 4-hour session limit.
    """
    now = require_utc(now_utc, "now_utc")
    started = require_utc(box_started_utc, "box_started_utc")

    if spot_stop_utc is not None:
        return Decision(
            Action.STOP_SPOT_WARNING,
            f"AWS will stop the box at {format_utc(require_utc(spot_stop_utc, 'spot_stop_utc'))}.",
        )
    if not nightly:
        if now - started >= WORK_SESSION_LIMIT:
            return Decision(Action.STOP_SESSION_LIMIT, "The work session reached its 4 hour limit.")
        return Decision(Action.KEEP_WAITING, "This is a work session, not the nightly run.")
    if progress in (RunProgress.SUCCEEDED, RunProgress.FAILED):
        return Decision(Action.STOP_FINISHED, f"The nightly run {progress.value}.")
    if reached_maximum(started, now):
        return Decision(Action.STOP_MAXIMUM, "The nightly run reached its 2 hour maximum.")
    return Decision(Action.KEEP_WAITING, "The nightly run is still inside its time limit.")


NIGHTLY_START_HOUR_UTC = 10
NIGHTLY_START_WINDOW = timedelta(minutes=30)


def is_nightly_boot(boot_utc: datetime) -> bool:
    """Return True when the box booted for the nightly run: within 30 minutes after 10:00 UTC.

    The schedule starts the box at 10:00 UTC. Any other boot is a work session that I started.
    """
    boot = require_utc(boot_utc, "boot_utc")
    scheduled = boot.replace(hour=NIGHTLY_START_HOUR_UTC, minute=0, second=0, microsecond=0)
    return timedelta(0) <= boot - scheduled <= NIGHTLY_START_WINDOW


def parse_spot_notice(body: str) -> datetime:
    """Read the notice that AWS puts in the instance metadata two minutes before a stop.

    The notice looks like ``{"action": "stop", "time": "2026-10-10T11:32:00Z"}``. Return the
    time the box will stop.
    """
    try:
        notice = json.loads(body)
        stop_time = notice["time"]
    except json.JSONDecodeError as error:
        raise ValueError("the spot notice is not valid JSON") from error
    except (KeyError, TypeError) as error:
        raise ValueError("the spot notice has no time") from error
    return require_utc(datetime.fromisoformat(stop_time), "time")


def fetch_spot_stop_time(request: Callable, base_url: str = METADATA_URL) -> datetime | None:
    """Ask the instance metadata service whether AWS has sent a stop notice.

    ``request(method, url, headers)`` returns ``(status, body)``. The service needs a token
    first, because the box requires version 2 of the metadata service. A 404 means no
    notice, which is the normal answer.
    """
    status, token = request(
        "PUT", f"{base_url}/latest/api/token", {"X-aws-ec2-metadata-token-ttl-seconds": "60"}
    )
    if status != 200:
        raise OSError(f"the metadata service refused a token with status {status}")

    status, body = request(
        "GET",
        f"{base_url}/latest/meta-data/spot/instance-action",
        {"X-aws-ec2-metadata-token": token},
    )
    if status == 404:
        return None
    if status == 200:
        return parse_spot_notice(body)
    raise OSError(f"unexpected status {status} from the metadata service")


def carry_out_stop(
    decision: Decision,
    save_database: Callable[[], None],
    record_incident: Callable[[Decision], None],
    send_alert: Callable[[Decision], None],
    power_off: Callable[[], None],
) -> list[str]:
    """Run the stop steps in order and return the errors from the steps that failed.

    The database is saved first, because it is the step with a deadline. An incident is
    recorded and an email sent only for the maximum and for a spot warning: the run did not
    finish, so nothing else reports it. Each step runs even if the one before it failed.
    Powering off is last and always runs, so a failed save can never leave a billing server on.
    If powering off itself fails, the error is raised, because nothing else can be done about it.
    """
    errors: list[str] = []
    try:
        save_database()
    except Exception as error:  # noqa: BLE001, a failed save must not stop the power-off
        errors.append(f"save_database failed: {error}")

    if decision.action in (Action.STOP_MAXIMUM, Action.STOP_SPOT_WARNING):
        for name, step in (("record_incident", record_incident), ("send_alert", send_alert)):
            try:
                step(decision)
            except Exception as error:  # noqa: BLE001, a failed step must not stop the power-off
                errors.append(f"{name} failed: {error}")

    power_off()
    return errors


def _or_default(read: Callable, default, what: str):  # noqa: ANN001, ANN202
    """Call ``read``. If it fails, log the error and return ``default``, so the loop goes on."""
    try:
        return read()
    except Exception as error:  # noqa: BLE001, one failed read must not end the watchdog
        logger.warning("Could not read %s: %s", what, error)
        return default


def watch(
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    box_started_utc: datetime,
    get_progress: Callable[[], RunProgress],
    get_spot_stop: Callable[[], datetime | None],
    on_stop: Callable[[Decision], None],
    poll_seconds: float = 30,
) -> Decision:
    """Poll until there is a reason to stop, call ``on_stop`` once, and return the decision.

    A read that fails counts as "nothing new". If Airflow cannot be reached, the watchdog
    still stops the box at the 2-hour maximum. A box that booted outside the nightly window is
    a work session, and only a spot warning or the 4-hour session limit stops it here.
    """
    nightly = is_nightly_boot(box_started_utc)
    while True:
        progress = _or_default(get_progress, RunProgress.WAITING, "the run state")
        spot_stop = _or_default(get_spot_stop, None, "the spot notice")
        decision = decide(now(), box_started_utc, progress, spot_stop, nightly)
        if decision.action is not Action.KEEP_WAITING:
            on_stop(decision)
            return decision
        sleep(poll_seconds)


def box_boot_time(now_utc: datetime, uptime_seconds: float) -> datetime:
    """Return when the box booted. The 2-hour clock starts then, not when the watchdog starts."""
    return require_utc(now_utc, "now_utc") - timedelta(seconds=uptime_seconds)


def list_runs_command(namespace: str, dag_id: str) -> list[str]:
    """Build the command that lists a DAG's runs as JSON, run inside the scheduler pod."""
    return [
        "kubectl",
        "exec",
        "--namespace",
        namespace,
        "airflow-scheduler-0",
        "--container",
        "scheduler",
        "--",
        "airflow",
        "dags",
        "list-runs",
        dag_id,
        "--output",
        "json",
    ]


def stop_incident(decision: Decision, number: int, opened_utc: datetime, pipeline: str) -> dict:
    """Build the incident for a stop that was not a normal finish."""
    if decision.action not in (Action.STOP_MAXIMUM, Action.STOP_SPOT_WARNING):
        raise ValueError(f"no incident is recorded for {decision.action.name}")
    return build_incident(
        number=number,
        opened_utc=opened_utc,
        pipeline=pipeline,
        what_broke=decision.reason,
        reached_maximum_runtime=decision.action is Action.STOP_MAXIMUM,
    )


def next_incident_number(client, bucket: str, now_utc: datetime) -> int:  # noqa: ANN001
    """Return the next unused incident number for the UTC date, from the incidents in S3."""
    day = require_utc(now_utc, "now_utc")
    prefix = f"platform/incidents/INC-{day:%Y-%m-%d}-"
    return len(airflow_db_backup.list_keys(client, bucket, prefix)) + 1


def http_request(method: str, url: str, headers: dict[str, str]) -> tuple[int, str]:
    """Make one web request and return ``(status, body)``. A 404 is an answer, not an error."""
    request = urllib.request.Request(url, method=method, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, ""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(description="Stop the session box when its work is done.")
    parser.add_argument("--bucket", required=True, help="the lake bucket for backups and incidents")
    parser.add_argument(
        "--env", required=True, choices=["dev", "live"], help="this box's environment"
    )
    parser.add_argument("--alert-topic-arn", required=True, help="the run alerts SNS topic")
    parser.add_argument("--namespace", default="airflow", help="Kubernetes namespace of Airflow")
    parser.add_argument("--dag-id", default="platform_skeleton_nightly", help="the nightly DAG")
    parser.add_argument("--poll-seconds", type=float, default=30, help="time between checks")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run on the box: watch the nightly run, then save the database and power off.

    This function connects the tested pieces above to the real machine, so it needs the real
    box to run. It reads the boot time from /proc/uptime, the run state from Airflow, and the
    spot notice from the metadata service.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import boto3  # Installed on the box by install.sh.

    client = boto3.client("s3")
    sns = boto3.client("sns")

    def now() -> datetime:
        return datetime.now(UTC)

    uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    boot = box_boot_time(now(), uptime)

    def get_progress() -> RunProgress:
        result = subprocess.run(
            list_runs_command(args.namespace, args.dag_id),
            capture_output=True,
            text=True,
            check=True,
        )
        return run_progress(result.stdout, boot)

    def save_database() -> None:
        airflow_db_backup.main(["save", "--bucket", args.bucket])

    def record_incident(decision: Decision) -> None:
        opened = now()
        number = next_incident_number(client, args.bucket, opened)
        incident = stop_incident(decision, number, opened, args.dag_id)
        with tempfile.TemporaryDirectory() as folder:
            write_incident(incident, Path(folder))
            upload_tree(client, args.bucket, "platform/incidents/", Path(folder))

    def send_alert(decision: Decision) -> None:
        alerts.send_alert(sns, args.alert_topic_arn, alerts.stop_alert(decision.reason, args.env))

    def power_off() -> None:
        subprocess.run(["systemctl", "poweroff"], check=True)

    def on_stop(decision: Decision) -> None:
        logger.info("Stopping the box. %s", decision.reason)
        for error in carry_out_stop(
            decision, save_database, record_incident, send_alert, power_off
        ):
            logger.error(error)

    watch(
        now=now,
        sleep=time.sleep,
        box_started_utc=boot,
        get_progress=get_progress,
        get_spot_stop=lambda: fetch_spot_stop_time(http_request),
        on_stop=on_stop,
        poll_seconds=args.poll_seconds,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
