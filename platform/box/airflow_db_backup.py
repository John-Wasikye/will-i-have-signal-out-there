"""Saves Airflow's database to S3 and restores it when a fresh box starts.

Airflow's PostgreSQL database lives on the session box, which is switched off most of the
time. The box saves the database to S3 after every run and at shutdown, and restores the
newest copy at startup. The backup holds no key: Airflow reads its connection keys from
Parameter Store, and the database commands run inside the PostgreSQL pod, which already holds
the password, so it never appears on a command line or leaves the pod.

I keep the newest copy and one before it. That is the default for open question OQ-P06.
"""

from __future__ import annotations

import argparse
import gzip
import shlex
import subprocess
import sys
import tempfile
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


def list_keys(client, bucket: str, prefix: str) -> list[str]:  # noqa: ANN001
    """List the keys under ``prefix``. ``client`` is a boto3 S3 client."""
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

    stale = keys_to_delete(list_keys(client, bucket, prefix), keep)
    if stale:
        client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in stale]})
    return key


def restore_latest(client, bucket: str, prefix: str, target_path: Path) -> bool:  # noqa: ANN001
    """Download the newest backup to ``target_path``. Return False on a first run with none."""
    latest = select_latest(list_keys(client, bucket, prefix))
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
    """Build the psql command that loads a dump.

    It stops at the first error, and the whole dump is one transaction, so a failed restore
    leaves the database as it was instead of half replaced.
    """
    return [
        "psql",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--single-transaction",
        "--set",
        "ON_ERROR_STOP=1",
        database,
    ]


def dump_to_file(command: list[str], target_path: Path, run=subprocess.run) -> None:  # noqa: ANN001
    """Run the dump command and write its output as a gzip file."""
    result = run(command, capture_output=True, check=True)
    target_path.write_bytes(gzip.compress(result.stdout))


def restore_from_file(command: list[str], source_path: Path, run=subprocess.run) -> None:  # noqa: ANN001
    """Send the text inside a gzip dump to the restore command."""
    run(command, input=gzip.decompress(source_path.read_bytes()), check=True)


def in_pod(command: list[str], namespace: str, pod: str, interactive: bool = False) -> list[str]:
    """Wrap a database command so it runs inside the PostgreSQL pod.

    The pod already holds the password in its POSTGRES_PASSWORD variable, so the command
    reads it there. The password never appears in a command line on the box.
    """
    inner = f'PGPASSWORD="$POSTGRES_PASSWORD" {shlex.join(command)}'
    exec_command = ["kubectl", "exec"]
    if interactive:
        exec_command.append("-i")
    return [*exec_command, "--namespace", namespace, pod, "--", "sh", "-c", inner]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Read the command line: ``save`` or ``restore``, and where the backups live."""
    parser = argparse.ArgumentParser(description="Save or restore Airflow's database in S3.")
    parser.add_argument("action", choices=["save", "restore"])
    parser.add_argument("--bucket", required=True, help="S3 bucket that holds the backups")
    parser.add_argument("--prefix", default="airflow-db/", help="folder inside the bucket")
    parser.add_argument("--namespace", default="airflow", help="Kubernetes namespace of Airflow")
    parser.add_argument("--pod", default="airflow-postgresql-0", help="the PostgreSQL pod")
    parser.add_argument("--database", default="postgres", help="database name")
    parser.add_argument("--user", default="postgres", help="database user")
    return parser.parse_args(argv)


def main(argv: list[str], client=None, run=subprocess.run, now: datetime | None = None) -> int:  # noqa: ANN001
    """Save or restore the database. ``client``, ``run`` and ``now`` are replaced in tests."""
    args = parse_args(argv)
    if client is None:
        import boto3  # Only the box needs it, and it is installed there.

        client = boto3.client("s3")
    now = now or datetime.now(UTC)
    connection = {"host": "localhost", "port": 5432, "user": args.user, "database": args.database}

    with tempfile.TemporaryDirectory() as folder:
        dump_path = Path(folder) / "airflow.sql.gz"
        if args.action == "save":
            command = in_pod(pg_dump_command(**connection), args.namespace, args.pod)
            dump_to_file(command, dump_path, run=run)
            key = save_backup(client, args.bucket, args.prefix, dump_path, now)
            print(f"Saved the database to s3://{args.bucket}/{key}")
            return 0

        if not restore_latest(client, args.bucket, args.prefix, dump_path):
            print("No backup found, so Airflow starts with an empty database.")
            return 0
        command = in_pod(psql_restore_command(**connection), args.namespace, args.pod, True)
        restore_from_file(command, dump_path, run=run)
        print("Restored the newest database backup.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
