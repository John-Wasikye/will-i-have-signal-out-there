"""Incident records (docs/platform/contracts/platform_incidents.yaml).

An incident is a short record of something that really broke: what broke, when, and in
which pipeline. The cause and the fix are filled in later, by hand. The incident files
stay in the private lake, and the public status page links only to the GitHub issue.

The error text of a failed task goes into the record, cut to a short length. It can name
files or tables, so these records are never published.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from timeutil import format_utc, require_utc

MAX_DESCRIPTION_LENGTH = 300

_SCHEMA = pa.schema(
    [
        ("incident_id", pa.string()),
        ("opened_at_utc", pa.timestamp("us", tz="UTC")),
        ("closed_at_utc", pa.timestamp("us", tz="UTC")),
        ("project", pa.string()),
        ("pipeline", pa.string()),
        ("what_broke", pa.string()),
        ("cause", pa.string()),
        ("fix", pa.string()),
        ("github_issue_url", pa.string()),
        ("reached_maximum_runtime", pa.bool_()),
        ("status", pa.string()),
    ]
)


def build_incident(
    number: int,
    opened_utc: datetime,
    pipeline: str,
    what_broke: str,
    reached_maximum_runtime: bool = False,
) -> dict:
    """Build a new open incident. The ID is the UTC date plus a two-digit number."""
    if number < 1:
        raise ValueError("number must be at least 1")
    opened = require_utc(opened_utc, "opened_utc")
    return {
        "incident_id": f"INC-{opened:%Y-%m-%d}-{number:02d}",
        "opened_at_utc": format_utc(opened),
        "project": "platform",
        "pipeline": pipeline,
        "what_broke": what_broke,
        "reached_maximum_runtime": reached_maximum_runtime,
        "status": "open",
    }


def failure_incident(number: int, opened_utc: datetime, dag_id: str, task_id: str, error: str):
    """Build the incident for a task that failed. The error text is cut to a short length."""
    description = f"Task {task_id} in {dag_id} failed: {error}"
    if len(description) > MAX_DESCRIPTION_LENGTH:
        description = description[: MAX_DESCRIPTION_LENGTH - 3] + "..."
    return build_incident(number, opened_utc, dag_id, description)


def write_incident(incident: dict, directory: Path) -> Path:
    """Write the incident as a Parquet file named after its ID, and return the path.

    Writing the same incident again replaces the file, so a retry does not add a second copy.
    """
    row = {name: incident.get(name) for name in _SCHEMA.names}
    row["opened_at_utc"] = datetime.strptime(incident["opened_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    row["opened_at_utc"] = row["opened_at_utc"].replace(tzinfo=UTC)

    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{incident['incident_id']}.parquet"
    partial = final.with_suffix(".parquet.part")
    pq.write_table(pa.Table.from_pylist([row], schema=_SCHEMA), partial, compression="zstd")
    os.replace(partial, final)
    return final


def record_failure(context: dict, directory: Path, now_utc: datetime | None = None) -> Path:
    """Airflow's failure callback: record one incident for the task that failed.

    ``context`` is the dictionary Airflow passes to a callback. The incident number is the
    next unused number for the UTC date of the failure.
    """
    now = require_utc(now_utc or datetime.now(UTC), "now_utc")
    existing = (
        len(list(directory.glob(f"INC-{now:%Y-%m-%d}-*.parquet"))) if directory.exists() else 0
    )
    incident = failure_incident(
        number=existing + 1,
        opened_utc=now,
        dag_id=context["dag"].dag_id,
        task_id=context["task_instance"].task_id,
        error=str(context.get("exception", "no error was reported")),
    )
    return write_incident(incident, directory)
