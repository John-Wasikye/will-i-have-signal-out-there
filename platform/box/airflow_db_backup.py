"""Saves Airflow's database to S3 and restores it when a fresh box starts.

Airflow's PostgreSQL database lives on the session box, which is switched off most of the
time. The box saves the database to S3 after every run and at shutdown, and restores the
newest copy at startup. The backup holds no key: Airflow reads its connection keys from
Parameter Store, and the database password reaches these commands only through the
PGPASSWORD environment variable, never on a command line.

I keep the newest copy and one before it. That is the default for open question OQ-P06.
"""

from __future__ import annotations

import gzip
import subprocess
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_KEEP = 2


def backup_key(prefix: str, now_utc: datetime) -> str:
    """Return the S3 key for a backup made at ``now_utc``. Keys sort by time as plain text."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware (UTC), got a naive datetime")
    return f"{prefix}airflow-db-{now_utc.astimezone(UTC):%Y%m%dT%H%M%SZ}.sql.gz"


def select_latest(keys: list[str]) -> str | None:
    """Return the newest backup key, or None when there are no backups."""
    return max(keys) if keys else None


def keys_to_delete(keys: list[str], keep: int) -> list[str]:
    """Return the oldest keys, leaving the newest ``keep`` of them."""
    if keep < 1:
        raise ValueError("keep must be at least 1, or the newest backup would be deleted")
    ordered = sorted(keys)
    return ordered[: max(len(ordered) - keep, 0)]


def list_backup_keys(client, bucket: str, prefix: str) -> list[str]:  # noqa: ANN001
    """List the backup keys under ``prefix``. ``client`` is a boto3 S3 client."""
    keys: list[str] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    return keys


def save_backup(
    client,  # noqa: ANN001
    bucket: str,
    prefix: str,
    dump_path: Path,
    now_utc: datetime,
    keep: int = DEFAULT_KEEP,
) -> str:
    """Upload the dump, then delete the oldest copies, and return the new key.

    The upload comes first, so a failed upload never leaves me without a backup.
    """
    key = backup_key(prefix, now_utc)
    client.upload_file(Filename=str(dump_path), Bucket=bucket, Key=key)

    stale = keys_to_delete(list_backup_keys(client, bucket, prefix), keep)
    if stale:
        client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in stale]})
    return key


def restore_latest(client, bucket: str, prefix: str, target_path: Path) -> bool:  # noqa: ANN001
    """Download the newest backup to ``target_path``. Return False on a first run with none."""
    latest = select_latest(list_backup_keys(client, bucket, prefix))
    if latest is None:
        return False
    client.download_file(Bucket=bucket, Key=latest, Filename=str(target_path))
    return True


def pg_dump_command(host: str, port: int, user: str, database: str) -> list[str]:
    """Build the pg_dump command. The password comes from the PGPASSWORD environment variable."""
    return [
        "pg_dump",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--no-owner",
        "--clean",
        "--if-exists",
        database,
    ]


def psql_restore_command(host: str, port: int, user: str, database: str) -> list[str]:
    """Build the psql command that loads a dump. It stops at the first error."""
    return [
        "psql",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--set",
        "ON_ERROR_STOP=1",
        database,
    ]


def dump_to_file(
    command: list[str],
    target_path: Path,
    environment: dict[str, str],
    run=subprocess.run,  # noqa: ANN001
) -> None:
    """Run the dump command and write its output as a gzip file."""
    result = run(command, capture_output=True, env=environment, check=True)
    target_path.write_bytes(gzip.compress(result.stdout))


def restore_from_file(
    command: list[str],
    source_path: Path,
    environment: dict[str, str],
    run=subprocess.run,  # noqa: ANN001
) -> None:
    """Send the text inside a gzip dump to the restore command."""
    run(command, input=gzip.decompress(source_path.read_bytes()), env=environment, check=True)
