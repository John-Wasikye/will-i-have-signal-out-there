"""Uploads the pipeline's outputs from the session box to S3.

The box is switched off most of the time, so nothing is live until its outputs are in S3
(engineering standard 16). Four things go up:

- the published Parquet files, to ``published/`` in the site bucket, where the API reads them
- status.json, to the root of the site bucket, where the status page reads it
- the run metrics and the incident records, to the lake bucket

status.json goes up last, so the status page never points at data that is not there yet.
Incident records are the exception to "the newest copy wins": the copy in S3 is the record,
and it is changed there when an incident closes, so an upload only adds records S3 lacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATUS_FILE = "status.json"
INCIDENTS_PREFIX = "platform/incidents/"

_CONTENT_TYPES = {
    ".parquet": "application/vnd.apache.parquet",
    ".json": "application/json",
}
_TEMPORARY_SUFFIXES = {".tmp", ".part"}


@dataclass(frozen=True)
class OutputLocations:
    """The two buckets that receive the outputs of one environment."""

    site_bucket: str
    lake_bucket: str


def _is_temporary(relative: Path) -> bool:
    """Return True for a half-written file: a dot-name, or one that ends in .tmp or .part."""
    return (
        any(part.startswith(".") for part in relative.parts)
        or relative.suffix in _TEMPORARY_SUFFIXES
    )


def _upload(client, path: Path, bucket: str, key: str) -> None:  # noqa: ANN001
    """Upload one file, with a content type when the file type is known."""
    content_type = _CONTENT_TYPES.get(path.suffix)
    extra_args = {"ContentType": content_type} if content_type else None
    client.upload_file(Filename=str(path), Bucket=bucket, Key=key, ExtraArgs=extra_args)


def upload_tree(
    client,  # noqa: ANN001
    bucket: str,
    prefix: str,
    directory: Path,
    exclude_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Upload every finished file under ``directory`` to ``prefix`` and return the keys.

    A folder that does not exist uploads nothing, because a night with no incidents has no
    incident folder. ``client`` is a boto3 S3 client.
    """
    if not prefix.endswith("/"):
        raise ValueError("prefix must end with a slash, for example 'published/'")

    keys: list[str] = []
    for path, key in _finished_files(prefix, directory, exclude_names):
        _upload(client, path, bucket, key)
        keys.append(key)
    return keys


def upload_new_files(client, bucket: str, prefix: str, directory: Path) -> list[str]:  # noqa: ANN001
    """Upload the finished files under ``directory`` that S3 does not have yet.

    Return the keys written. A key that already exists is left as it is, so a record changed
    in S3, such as a closed incident, is never put back by an older copy on the box. S3 checks
    the condition itself, so two writers of the same key cannot both win.
    """
    keys: list[str] = []
    for path, key in _finished_files(prefix, directory, frozenset()):
        if put_if_new(client, path, bucket, key):
            keys.append(key)
    return keys


def put_if_new(client, path: Path, bucket: str, key: str) -> bool:  # noqa: ANN001
    """Put one file only if ``key`` is free. Return False when S3 already has the key."""
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=path.read_bytes(),
            IfNoneMatch="*",
            ContentType=_CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
        )
    except Exception as error:
        if s3_error_code(error) == "PreconditionFailed":
            return False
        raise
    return True


def s3_error_code(error: Exception) -> str | None:
    """Return the S3 error code carried by a boto3 error, or None for any other error."""
    return getattr(error, "response", {}).get("Error", {}).get("Code")


def _finished_files(prefix: str, directory: Path, exclude_names: frozenset[str]):
    """Yield ``(path, key)`` for each finished file under ``directory``, in a stable order."""
    if not prefix.endswith("/"):
        raise ValueError("prefix must end with a slash, for example 'published/'")
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if path.is_file() and not _is_temporary(relative) and path.name not in exclude_names:
            yield path, prefix + relative.as_posix()


def upload_outputs(
    client,  # noqa: ANN001
    locations: OutputLocations,
    published_dir: Path,
    metrics_dir: Path,
    incidents_dir: Path,
) -> list[str]:
    """Upload all four kinds of output, with status.json last. Return what was uploaded."""
    uploaded = [
        f"s3://{locations.site_bucket}/{key}"
        for key in upload_tree(
            client,
            locations.site_bucket,
            "published/",
            published_dir,
            exclude_names=frozenset({STATUS_FILE}),
        )
    ]
    uploaded += [
        f"s3://{locations.lake_bucket}/{key}"
        for key in upload_tree(client, locations.lake_bucket, "platform/run_metrics/", metrics_dir)
    ]
    uploaded += [
        f"s3://{locations.lake_bucket}/{key}"
        for key in upload_new_files(client, locations.lake_bucket, INCIDENTS_PREFIX, incidents_dir)
    ]

    status_path = published_dir / STATUS_FILE
    if status_path.is_file():
        _upload(client, status_path, locations.site_bucket, STATUS_FILE)
        uploaded.append(f"s3://{locations.site_bucket}/{STATUS_FILE}")
    return uploaded
