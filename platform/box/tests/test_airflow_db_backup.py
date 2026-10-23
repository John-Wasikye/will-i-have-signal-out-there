"""Tests for saving Airflow's database to S3 and restoring it on a fresh box.

The rules come from the decision record for the Airflow database: it is saved after every
run and at shutdown, restored at startup, and the backup holds no key. I keep the latest
copy plus one previous copy (the default for open question OQ-P06).
"""

from datetime import UTC, datetime

import pytest
from airflow_db_backup import (
    backup_key,
    keys_to_delete,
    pg_dump_command,
    psql_restore_command,
    restore_latest,
    save_backup,
    select_latest,
)

PREFIX = "airflow-db/"
NOW = datetime(2026, 10, 10, 10, 45, 5, tzinfo=UTC)


class FakeS3:
    """Holds objects in memory and records the order of calls."""

    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.calls: list[str] = []

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket: str, Prefix: str):  # noqa: N803, boto3 parameter names
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        yield {"Contents": [{"Key": key} for key in keys]} if keys else {}

    def upload_file(self, Filename: str, Bucket: str, Key: str):  # noqa: N803, boto3 names
        self.calls.append(f"upload:{Key}")
        with open(Filename, "rb") as handle:
            self.objects[Key] = handle.read()

    def download_file(self, Bucket: str, Key: str, Filename: str):  # noqa: N803, boto3 names
        self.calls.append(f"download:{Key}")
        with open(Filename, "wb") as handle:
            handle.write(self.objects[Key])

    def delete_objects(self, Bucket: str, Delete: dict):  # noqa: N803, boto3 parameter names
        for item in Delete["Objects"]:
            self.calls.append(f"delete:{item['Key']}")
            del self.objects[item["Key"]]


def test_the_backup_key_holds_the_utc_time_and_sorts_by_time():
    assert backup_key(PREFIX, NOW) == "airflow-db/airflow-db-20261010T104505Z.sql.gz"


def test_the_backup_key_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        backup_key(PREFIX, datetime(2026, 10, 10, 10, 45))


def test_the_latest_key_is_the_newest_one():
    keys = [
        "airflow-db/airflow-db-20261008T100000Z.sql.gz",
        "airflow-db/airflow-db-20261010T100000Z.sql.gz",
        "airflow-db/airflow-db-20261009T100000Z.sql.gz",
    ]
    assert select_latest(keys) == "airflow-db/airflow-db-20261010T100000Z.sql.gz"


def test_there_is_no_latest_key_when_there_are_no_backups():
    assert select_latest([]) is None


def test_all_but_the_newest_two_keys_are_deleted():
    keys = [f"airflow-db/airflow-db-2026100{day}T100000Z.sql.gz" for day in range(1, 6)]
    assert keys_to_delete(keys, keep=2) == keys[:3]


def test_nothing_is_deleted_when_there_are_two_or_fewer_keys():
    keys = ["airflow-db/airflow-db-20261001T100000Z.sql.gz"]
    assert keys_to_delete(keys, keep=2) == []


def test_saving_uploads_first_and_only_then_deletes_the_oldest(tmp_path):
    old = {
        "airflow-db/airflow-db-20261007T100000Z.sql.gz": b"a",
        "airflow-db/airflow-db-20261008T100000Z.sql.gz": b"b",
        "airflow-db/airflow-db-20261009T100000Z.sql.gz": b"c",
    }
    s3 = FakeS3(old)
    dump = tmp_path / "dump.sql.gz"
    dump.write_bytes(b"new")

    key = save_backup(s3, "bucket", PREFIX, dump, NOW, keep=2)

    assert key == "airflow-db/airflow-db-20261010T104505Z.sql.gz"
    assert s3.calls[0] == f"upload:{key}"
    assert s3.calls[1:] == [
        "delete:airflow-db/airflow-db-20261007T100000Z.sql.gz",
        "delete:airflow-db/airflow-db-20261008T100000Z.sql.gz",
    ]
    assert sorted(s3.objects) == [
        "airflow-db/airflow-db-20261009T100000Z.sql.gz",
        key,
    ]


def test_a_failed_upload_deletes_nothing(tmp_path):
    class BrokenUpload(FakeS3):
        def upload_file(self, Filename: str, Bucket: str, Key: str):  # noqa: N803
            raise OSError("network down")

    s3 = BrokenUpload({"airflow-db/airflow-db-20261009T100000Z.sql.gz": b"c"})
    dump = tmp_path / "dump.sql.gz"
    dump.write_bytes(b"new")

    with pytest.raises(OSError, match="network down"):
        save_backup(s3, "bucket", PREFIX, dump, NOW, keep=2)

    assert list(s3.objects) == ["airflow-db/airflow-db-20261009T100000Z.sql.gz"]


def test_restoring_downloads_the_newest_backup(tmp_path):
    s3 = FakeS3(
        {
            "airflow-db/airflow-db-20261009T100000Z.sql.gz": b"older",
            "airflow-db/airflow-db-20261010T100000Z.sql.gz": b"newest",
        }
    )
    target = tmp_path / "restore.sql.gz"

    restored = restore_latest(s3, "bucket", PREFIX, target)

    assert restored is True
    assert target.read_bytes() == b"newest"


def test_restoring_on_a_first_run_finds_nothing_and_says_so(tmp_path):
    target = tmp_path / "restore.sql.gz"

    restored = restore_latest(FakeS3(), "bucket", PREFIX, target)

    assert restored is False
    assert not target.exists()


def test_the_dump_command_names_the_database_and_carries_no_password():
    command = pg_dump_command(host="localhost", port=5432, user="airflow", database="airflow")

    assert command[0] == "pg_dump"
    assert "airflow" in command
    assert not any("password" in part.lower() for part in command)


def test_the_restore_command_names_the_database_and_carries_no_password():
    command = psql_restore_command(host="localhost", port=5432, user="airflow", database="airflow")

    assert command[0] == "psql"
    assert "airflow" in command
    assert not any("password" in part.lower() for part in command)


class FakeRun:
    """Stands in for subprocess.run and records what it was given."""

    def __init__(self, stdout: bytes = b""):
        self.stdout = stdout
        self.command = None
        self.input = None
        self.env = None

    def __call__(self, command, **kwargs):
        self.command = command
        self.input = kwargs.get("input")
        self.env = kwargs.get("env")

        class Result:
            pass

        result = Result()
        result.stdout = self.stdout
        return result


def test_dumping_writes_the_database_text_as_a_gzip_file(tmp_path):
    import gzip

    from airflow_db_backup import dump_to_file

    run = FakeRun(stdout=b"CREATE TABLE dag;\n")
    target = tmp_path / "dump.sql.gz"

    dump_to_file(["pg_dump", "airflow"], target, run=run)

    assert gzip.decompress(target.read_bytes()) == b"CREATE TABLE dag;\n"
    assert run.command == ["pg_dump", "airflow"]
    # The password stays inside the database pod (see in_pod), so the box passes none.
    assert run.env is None


def test_restoring_sends_the_decompressed_text_to_the_database(tmp_path):
    import gzip

    from airflow_db_backup import restore_from_file

    source = tmp_path / "dump.sql.gz"
    source.write_bytes(gzip.compress(b"CREATE TABLE dag;\n"))
    run = FakeRun()

    restore_from_file(["psql", "airflow"], source, run=run)

    assert run.input == b"CREATE TABLE dag;\n"
    assert run.command == ["psql", "airflow"]
    assert run.env is None


def test_a_command_runs_inside_the_database_pod_and_reads_the_password_there():
    from airflow_db_backup import in_pod

    wrapped = in_pod(["pg_dump", "postgres"], namespace="airflow", pod="airflow-postgresql-0")

    assert wrapped[:6] == [
        "kubectl",
        "exec",
        "--namespace",
        "airflow",
        "airflow-postgresql-0",
        "--",
    ]
    inner = wrapped[-1]
    assert 'PGPASSWORD="$POSTGRES_PASSWORD"' in inner
    assert "pg_dump postgres" in inner
    assert "-i" not in wrapped[:3]


def test_a_restore_command_keeps_standard_input_open():
    from airflow_db_backup import in_pod

    wrapped = in_pod(["psql", "postgres"], namespace="airflow", pod="p", interactive=True)

    assert wrapped[:3] == ["kubectl", "exec", "-i"]


def test_the_command_line_has_save_and_restore_with_sensible_defaults():
    from airflow_db_backup import parse_args

    saved = parse_args(["save", "--bucket", "b"])
    restored = parse_args(["restore", "--bucket", "b"])

    assert saved.action == "save"
    assert restored.action == "restore"
    assert saved.prefix == "airflow-db/"
    assert saved.namespace == "airflow"
    assert saved.pod == "airflow-postgresql-0"


def test_the_command_line_needs_a_bucket():
    from airflow_db_backup import parse_args

    with pytest.raises(SystemExit):
        parse_args(["save"])


def test_save_dumps_the_database_in_the_pod_and_uploads_the_result():
    import gzip

    from airflow_db_backup import main

    s3 = FakeS3()
    run = FakeRun(stdout=b"CREATE TABLE dag;\n")

    exit_code = main(["save", "--bucket", "b"], client=s3, run=run, now=NOW)

    assert exit_code == 0
    assert run.command[:2] == ["kubectl", "exec"]
    assert "pg_dump" in run.command[-1]
    (key,) = s3.objects
    assert key == "airflow-db/airflow-db-20261010T104505Z.sql.gz"
    assert gzip.decompress(s3.objects[key]) == b"CREATE TABLE dag;\n"


def test_restore_loads_the_newest_backup_into_the_pod():
    import gzip

    from airflow_db_backup import main

    s3 = FakeS3({"airflow-db/airflow-db-20261009T100000Z.sql.gz": gzip.compress(b"SELECT 1;\n")})
    run = FakeRun()

    exit_code = main(["restore", "--bucket", "b"], client=s3, run=run, now=NOW)

    assert exit_code == 0
    assert run.command[:3] == ["kubectl", "exec", "-i"]
    assert "psql" in run.command[-1]
    assert run.input == b"SELECT 1;\n"


def test_restore_on_a_first_run_has_nothing_to_load_and_still_succeeds(capsys):
    from airflow_db_backup import main

    run = FakeRun()

    exit_code = main(["restore", "--bucket", "b"], client=FakeS3(), run=run, now=NOW)

    assert exit_code == 0
    assert run.command is None
    assert "No backup found" in capsys.readouterr().out


def test_the_file_runs_as_a_script_and_asks_for_a_bucket():
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent / "airflow_db_backup.py"

    result = subprocess.run(
        [sys.executable, str(script), "save"], capture_output=True, text=True, check=False
    )

    assert result.returncode == 2
    assert "--bucket" in result.stderr
