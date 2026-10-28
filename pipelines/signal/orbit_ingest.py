"""Orbit ingest (C1): pull the CelesTrak Starlink list and keep it, checked, for the selector.

Steps, each a function so a task can run them in order:

1. ``fetch_gp_json`` calls CelesTrak. CelesTrak updates the list every 2 hours and asks clients
   not to pull more often, so a second call within 2 hours is refused without a request. Any
   response other than HTTP 200, or an empty body, stops the pull (design doc 8.1, step 2).
2. ``store_raw`` keeps the file exactly as received, with a manifest of URL, fetch time, size
   and SHA-256 hash (engineering standard 1). It never replaces a file: live raw files are
   locked for 30 days anyway (ADR-0019).
3. ``parse_gp_records`` checks the file's fields against the contract (C8) before anything is
   loaded, so an upstream change fails here and names the field.
4. ``lake_rows`` renames each field to its contract column and adds the manifest columns.
5. ``load_gp_partition`` writes the rows to the Iceberg table, one partition per run date.

Timestamps are UTC (engineering standard 15). CelesTrak writes ``EPOCH`` without a zone; it is
UTC by definition of the GP format.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml
from contract_diff import (
    assert_no_breaking_change,
    diff_schema,
    load_contract,
    observed_schema_from_records,
)
from lake_write import write_run_partition
from raw_store import FetchRefused, RawFile, download, write_raw
from timeutil import format_utc, require_utc

CELESTRAK_STARLINK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"
MIN_TIME_BETWEEN_FETCHES = timedelta(hours=2)
RAW_PREFIX = "signal/celestrak/gp"
TABLE_NAME = "celestrak_gp"


def fetch_gp_json(
    url: str,
    last_fetch_time: datetime | None,
    *,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
) -> RawFile:
    """Download the GP JSON once, refusing a call within 2 hours of the last one."""
    now_utc = require_utc(now_utc, "now_utc")
    if last_fetch_time is not None:
        since = now_utc - require_utc(last_fetch_time, "last_fetch_time")
        if since < MIN_TIME_BETWEEN_FETCHES:
            raise FetchRefused(
                f"the last pull was {since} ago; CelesTrak is pulled at most once in 2 hours"
            )
    return download(url, now_utc=now_utc, opener=opener)


def raw_key(fetched_at: datetime) -> str:
    """Return the raw bucket key for a pull made at ``fetched_at``."""
    return f"{RAW_PREFIX}/fetched_at={format_utc(fetched_at)}/starlink.json"


def store_raw(client, bucket: str, raw: RawFile) -> dict:  # noqa: ANN001, a boto3 S3 client
    """Write the file unchanged and its manifest to the raw bucket, and return the manifest.

    Both writes use If-None-Match, so an existing raw file is never replaced.
    """
    key = raw_key(raw.fetched_at)
    return write_raw(client, bucket, key, key.rsplit("/", 1)[0] + "/manifest.json", raw)


def parse_gp_records(body: bytes, contract_path: Path) -> list[dict]:
    """Parse the GP JSON and stop if its fields no longer match the contract."""
    records = json.loads(body)
    if not isinstance(records, list):
        raise ValueError("the GP file is not a list of element sets")
    diff = diff_schema(load_contract(contract_path), observed_schema_from_records(records))
    assert_no_breaking_change(diff, "celestrak_gp")
    return records


def lake_rows(records: list[Mapping], manifest: Mapping, contract_path: Path) -> list[dict]:
    """Rename each record to the contract's lake columns and add the manifest columns."""
    columns = _upstream_columns(contract_path)
    fetched_at = datetime.strptime(manifest["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    added = {
        "source_url": manifest["source_url"],
        "fetched_at_utc": fetched_at.replace(tzinfo=UTC),
        "content_sha256": manifest["content_sha256"],
    }
    rows = []
    for record in records:
        row = {column: record[field] for field, column in columns.items()}
        row["epoch_utc"] = datetime.fromisoformat(row["epoch_utc"]).replace(tzinfo=UTC)
        rows.append(row | added)
    return rows


def _upstream_columns(contract_path: Path) -> dict[str, str]:
    """Map each upstream field the contract reads to its lake column name."""
    contract = yaml.safe_load(Path(contract_path).read_text(encoding="utf-8"))
    columns = {}
    for table in contract["schema"]:
        for column in table["properties"]:
            for item in column.get("customProperties", []):
                if item["property"] == "upstreamField":
                    columns[item["value"]] = column["name"]
    return columns


def load_gp_partition(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    rows: list[dict],
    run_date: date,
    *,
    namespace: str,
) -> int:
    """Write the rows as the run date's partition of ``celestrak_gp`` and return the row count.

    The partition is the run's logical date, not the fetch time (engineering standard 3), so a
    rerun of the same night replaces only that night's rows.
    """
    return write_run_partition(spark, TABLE_NAME, rows, run_date, namespace=namespace)
