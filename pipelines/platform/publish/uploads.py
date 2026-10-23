"""Uploads the pipeline's outputs from the session box to S3.

The box is switched off most of the time, so nothing is live until its outputs are in S3
(engineering standard 16). Four things go up:

- the published Parquet files, to ``published/`` in the site bucket, where the API reads them
- status.json, to the root of the site bucket, where the status page reads it
- the run metrics and the incident records, to the lake bucket

status.json goes up last, so the status page never points at data that is not there yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATUS_FILE = "status.json"

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
    if not directory.is_dir():
        return []

    keys: list[str] = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or _is_temporary(relative) or path.name in exclude_names:
            continue
        key = prefix + relative.as_posix()
        _upload(client, path, bucket, key)
        keys.append(key)
    return keys


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
    for prefix, directory in (
        ("platform/run_metrics/", metrics_dir),
        ("platform/incidents/", incidents_dir),
    ):
        uploaded += [
            f"s3://{locations.lake_bucket}/{key}"
            for key in upload_tree(client, locations.lake_bucket, prefix, directory)
        ]

    status_path = published_dir / STATUS_FILE
    if status_path.is_file():
        _upload(client, status_path, locations.site_bucket, STATUS_FILE)
        uploaded.append(f"s3://{locations.site_bucket}/{STATUS_FILE}")
    return uploaded
