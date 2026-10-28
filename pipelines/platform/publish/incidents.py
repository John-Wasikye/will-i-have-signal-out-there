"""Incident records (docs/platform/contracts/platform_incidents.yaml).

An incident is a short record of something that really broke: what broke, when, and in
which pipeline. The cause and the fix are filled in later, by hand. The incident files
stay in the private lake, and the public status page links only to the GitHub issue.

The copy in S3 is the record. A new incident is filed there as soon as it opens, and its
number is the next one free that day in S3, so a replaced box never reuses a number.

The error text of a failed task goes into the record, cut to a short length. It can name
files or tables, so these records are never published.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from timeutil import format_utc, require_utc
from uploads import INCIDENTS_PREFIX, put_if_new

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


def next_incident_number(taken: Iterable[str], day_utc: datetime) -> int:
    """Return one more than the highest incident number used on the UTC date of ``day_utc``.

    ``taken`` holds S3 keys or file names; anything that is not an incident of that day is
    ignored.
    """
    day = require_utc(day_utc, "day_utc")
    pattern = re.compile(rf"INC-{day:%Y-%m-%d}-(\d+)\.parquet$")
    numbers = [int(match.group(1)) for name in taken if (match := pattern.search(name))]
    return max(numbers, default=0) + 1


def file_incident(
    client,  # noqa: ANN001
    bucket: str,
    build: Callable[[int], dict],
    opened_utc: datetime,
    directory: Path,
    attempts: int = 5,
) -> str:
    """File a new incident in S3 under the next free number, and return its key.

    ``build`` makes the incident for a given number. The number counts what S3 and
    ``directory`` already hold for the day. If another writer files that number first, the
    file is removed and the next number is tried. If S3 cannot be reached, the file stays in
    ``directory``, and the nightly upload files it later. ``client`` is a boto3 S3 client.
    """
    opened = require_utc(opened_utc, "opened_utc")
    for _ in range(attempts):
        taken = _keys(client, bucket, f"{INCIDENTS_PREFIX}INC-{opened:%Y-%m-%d}-")
        taken += (
            [path.name for path in directory.glob("INC-*.parquet")] if directory.exists() else []
        )
        path = write_incident(build(next_incident_number(taken, opened)), directory)
        key = INCIDENTS_PREFIX + path.name
        if put_if_new(client, path, bucket, key):
            return key
        path.unlink()
    raise RuntimeError(
        f"could not file an incident in {attempts} attempts; numbers kept being taken"
    )


def _keys(client, bucket: str, prefix: str) -> list[str]:  # noqa: ANN001
    """List the keys under ``prefix``."""
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def record_failure(
    context: dict,
    directory: Path,
    client,  # noqa: ANN001
    bucket: str,
    now_utc: datetime | None = None,
) -> str:
    """Airflow's failure callback: file one incident for the task that failed.

    ``context`` is the dictionary Airflow passes to a callback. Return the S3 key.
    """
    now = require_utc(now_utc or datetime.now(UTC), "now_utc")
    return file_incident(
        client,
        bucket,
        lambda number: failure_incident(
            number=number,
            opened_utc=now,
            dag_id=context["dag"].dag_id,
            task_id=context["task_instance"].task_id,
            error=str(context.get("exception", "no error was reported")),
        ),
        now,
        directory,
    )
