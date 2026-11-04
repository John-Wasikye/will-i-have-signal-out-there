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
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path

from dtc_selector import disagreement_rows, satellite_rows, select_dtc_satellites
from elevation_source import (
    MANIFEST_PREFIX,
    fetch_tiles,
    store_tile_manifest,
    tiles_covering,
)
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
from terrain_horizon import RANGE_M, compute_horizons, validate_horizon
from timeutil import require_utc
from trail_loader import (
    PHASE_A_TRAILS,
    PHASE_A_UNIT_CODE,
    POINT_SPACING_M,
    TrailPoint,
    fetch_trail_pages,
    load_trail_tables,
    parse_trail_geojson,
    select_trails,
    store_trail_pages,
    trail_line_rows,
    trail_point_rows,
)

# Tiles reach 1 km past the horizon range, so no ray from a point near a tile edge runs off them.
TILE_MARGIN_M = 1_000


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


def compute_horizons_if_needed(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    now_utc: datetime,
    work_dir: Path,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """Give the newest trail points their terrain horizons, unless they already have them (C4).

    The horizon is reference data: it changes only when the trail points do (ADR 0028), so it is
    computed when the newest ``trail_point`` partition is newer than the newest horizon partition.
    The GLO-30 tiles are downloaded into ``work_dir`` and only their manifest is kept. Returns
    ``{"changed": False}``, or how many points and tiles were used.
    """
    points_table = f"{CATALOG_NAME}.{namespace}.trail_point"
    horizon_table = f"{CATALOG_NAME}.{namespace}.trail_point_horizon"
    points_date = _newest_run_date(spark, points_table)
    if points_date is None:
        raise ValueError("no trail points are loaded yet, so there is nothing to give a horizon")
    horizon_date = _newest_run_date(spark, horizon_table)
    if horizon_date is not None and horizon_date >= points_date:
        return {"changed": False}

    points = _trail_points(spark, points_table, points_date)
    tiles = tiles_covering(points, margin_m=RANGE_M + TILE_MARGIN_M)
    tile_rows = fetch_tiles(tiles, work_dir, now_utc=now_utc, opener=opener)
    kept = store_tile_manifest(
        s3,
        raw_bucket,
        tile_rows,
        previous=latest_manifest(s3, raw_bucket, MANIFEST_PREFIX),
        fetched_at=now_utc,
    )
    tile_paths = [Path(work_dir) / Path(row["tile_key"]).name for row in tile_rows]
    horizons = compute_horizons(spark, points, tile_paths)
    for horizon in horizons:
        problems = validate_horizon(horizon)
        if problems:
            raise ValueError(f"horizon for {horizon.trail_point_id}: {'; '.join(problems)}")

    rows = [
        {
            "trail_point_id": horizon.trail_point_id,
            "horizon_angles_deg": list(horizon.angles_deg),
            "computed_at_utc": now_utc,
            "elevation_source_manifest_sha256": kept["manifest_sha256"],
        }
        for horizon in horizons
    ]
    write_run_partition(
        spark,
        "trail_point_horizon",
        rows,
        run_date,
        columns=contract_columns(
            Path(contracts_dir) / "trail_point_horizon.yaml", "trail_point_horizon"
        ),
        namespace=namespace,
    )
    return {"changed": True, "points": len(points), "tiles": len(tiles)}


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


def _newest_run_date(spark, table: str) -> date | None:  # noqa: ANN001
    """Return the newest ``run_date`` partition of the table, or None if it has none."""
    if not spark.catalog.tableExists(table):
        return None
    return spark.sql(f"SELECT MAX(run_date) AS newest FROM {table}").collect()[0]["newest"]


def _trail_points(spark, table: str, run_date: date) -> list[TrailPoint]:  # noqa: ANN001
    """Return the trail points of one partition, in trail and sequence order."""
    names = [field.name for field in fields(TrailPoint)]
    query = (
        f"SELECT {', '.join(names)} FROM {table} "
        f"WHERE run_date = DATE '{run_date.isoformat()}' ORDER BY trail_id, seq"
    )
    return [TrailPoint(**{name: row[name] for name in names}) for row in spark.sql(query).collect()]
