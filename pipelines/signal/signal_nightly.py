"""The steps of the Phase A nightly run (design doc 8.1), as the DAG calls them.

Each function is one Airflow task. They pass only a manifest between them, so a task can run
again on its own: every step reads the raw file the pull kept, never a copy in Airflow.

1. ``pull_orbits`` (C1) pulls CelesTrak and keeps the file, or reuses a pull made in the last 2
   hours, because CelesTrak asks for at most one pull per 2-hour update. A retry or a cleared
   run therefore never pulls twice.
2. ``check_orbit_schema`` (C8) checks the kept file against the contract before anything loads.
3. ``load_orbits`` (C1) writes ``celestrak_gp`` for the run date.
4. ``select_and_load_dtc`` (C2) writes ``dtc_satellite`` and ``dtc_disagreement``.
5. ``load_trails_if_changed`` (C3) pulls the NPS trails and loads ``nps_trail_line`` and
   ``trail_point`` only when the pages differ from the last load (ADR 0028).
"""

from __future__ import annotations

import hashlib
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from dtc_selector import disagreement_rows, satellite_rows, select_dtc_satellites
from lake_write import contract_columns, write_run_partition
from orbit_ingest import (
    CELESTRAK_STARLINK_URL,
    MIN_TIME_BETWEEN_FETCHES,
    RAW_PREFIX,
    fetch_gp_json,
    lake_rows,
    load_gp_partition,
    parse_gp_records,
    store_raw,
)
from raw_store import latest_manifest, read_raw
from sample_iceberg_job import CATALOG_NAME
from timeutil import require_utc
from trail_loader import (
    PHASE_A_TRAILS,
    PHASE_A_UNIT_CODE,
    POINT_SPACING_M,
    fetch_trail_pages,
    load_trail_tables,
    parse_trail_geojson,
    select_trails,
    store_trail_pages,
    trail_line_rows,
    trail_point_rows,
)


def pull_orbits(
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    *,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """Return the manifest of a CelesTrak pull from the last 2 hours, pulling only if none."""
    now_utc = require_utc(now_utc, "now_utc")
    latest = latest_manifest(s3, raw_bucket, RAW_PREFIX)
    last_fetch = None
    if latest is not None:
        last_fetch = datetime.strptime(latest["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
        last_fetch = last_fetch.replace(tzinfo=UTC)
        if now_utc - last_fetch < MIN_TIME_BETWEEN_FETCHES:
            return latest
    raw = fetch_gp_json(CELESTRAK_STARLINK_URL, last_fetch, now_utc=now_utc, opener=opener)
    return store_raw(s3, raw_bucket, raw)


def check_orbit_schema(
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    manifest: dict,
    contracts_dir: Path,
) -> int:
    """Check the kept CelesTrak file against its contract and return its record count."""
    body = read_raw(s3, raw_bucket, manifest["raw_key"])
    return len(parse_gp_records(body, Path(contracts_dir) / "celestrak_gp.yaml"))


def load_orbits(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    manifest: dict,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
) -> int:
    """Write the kept CelesTrak file to ``celestrak_gp`` for the run date; return the count."""
    contract = Path(contracts_dir) / "celestrak_gp.yaml"
    rows = _orbit_rows(s3, raw_bucket, manifest, contract)
    return load_gp_partition(spark, rows, run_date, contract_path=contract, namespace=namespace)


def select_and_load_dtc(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    manifest: dict,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
) -> dict[str, int]:
    """Select the Direct-to-Cell satellites and write both tables; return each row count.

    A night with no disagreement is normal, so ``dtc_disagreement`` may be empty.
    """
    contracts = Path(contracts_dir)
    rows = _orbit_rows(s3, raw_bucket, manifest, contracts / "celestrak_gp.yaml")
    selected, disagreements = select_dtc_satellites(rows)
    pull = {
        "fetched_at_utc": rows[0]["fetched_at_utc"],
        "content_sha256": manifest["content_sha256"],
    }
    return {
        "dtc_satellite": write_run_partition(
            spark,
            "dtc_satellite",
            satellite_rows(selected),
            run_date,
            columns=contract_columns(contracts / "dtc_satellite.yaml", "dtc_satellite"),
            namespace=namespace,
        ),
        "dtc_disagreement": write_run_partition(
            spark,
            "dtc_disagreement",
            disagreement_rows(disagreements, pull),
            run_date,
            columns=contract_columns(contracts / "dtc_disagreement.yaml", "dtc_disagreement"),
            namespace=namespace,
            allow_empty=True,
        ),
    }


def load_trails_if_changed(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """Pull the Phase A park's trails; keep and load them only if the pages changed.

    The pages are compared with the hashes of the pages the last load came from, read from
    ``nps_trail_line``, not with the last pull kept in S3: a pull that was kept but never loaded
    must still be loaded. Returns ``{"changed": False}``, or the row count of each table.
    """
    contracts = Path(contracts_dir)
    pages = fetch_trail_pages(PHASE_A_UNIT_CODE, now_utc=now_utc, opener=opener)
    page_hashes = {hashlib.sha256(page.body).hexdigest() for page in pages}
    if page_hashes == _loaded_trail_hashes(spark, namespace):
        return {"changed": False}

    manifests = store_trail_pages(s3, raw_bucket, pages)
    page_of_line = {}
    lines = []
    for number, page in enumerate(pages):
        for line in parse_trail_geojson(page.body, contracts / "nps_trails.yaml"):
            page_of_line[line.trail_line_id] = number
            lines.append(line)
    selected = select_trails(lines, PHASE_A_TRAILS)
    line_rows = [
        row
        for number, manifest in enumerate(manifests)
        for row in trail_line_rows(
            [line for line in selected if page_of_line[line.trail_line_id] == number], manifest
        )
    ]
    counts = load_trail_tables(
        spark,
        line_rows,
        trail_point_rows(selected, POINT_SPACING_M),
        run_date,
        line_contract_path=contracts / "nps_trails.yaml",
        point_contract_path=contracts / "trail_point.yaml",
        namespace=namespace,
    )
    return {"changed": True, **counts}


def _orbit_rows(s3, raw_bucket: str, manifest: dict, contract: Path) -> list[dict]:  # noqa: ANN001
    """Read the kept CelesTrak file, check it against the contract, and shape its rows."""
    records = parse_gp_records(read_raw(s3, raw_bucket, manifest["raw_key"]), contract)
    return lake_rows(records, manifest, contract)


def _loaded_trail_hashes(spark, namespace: str) -> set[str]:  # noqa: ANN001
    """Return the page hashes of the newest ``nps_trail_line`` partition, or none."""
    table = f"{CATALOG_NAME}.{namespace}.nps_trail_line"
    if not spark.catalog.tableExists(table):
        return set()
    query = (
        f"SELECT DISTINCT content_sha256 FROM {table} "
        f"WHERE run_date = (SELECT MAX(run_date) FROM {table})"
    )
    return {row["content_sha256"] for row in spark.sql(query).collect()}
