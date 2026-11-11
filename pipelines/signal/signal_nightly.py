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
6. ``compute_horizons_if_needed`` (C4) gives new trail points their terrain horizons.
7. ``compute_windows`` (C5) writes ``satellite_window``: when each selected satellite is
   reachable from each trail point over the next 26 hours.
8. ``load_coverage_if_changed`` (C6) loads the kept FCC file and flags each trail point, only
   when the file or the points changed (ADR 0028).
9. ``ookla_quarter_to_load`` and ``load_ookla_quarter`` (C13) load Ookla's newest quarter of
   Arizona speed-test tiles into ``ookla_tile``, once per quarter.
"""

from __future__ import annotations

import hashlib
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dtc_selector import disagreement_rows, satellite_rows, select_dtc_satellites
from elevation_source import (
    MANIFEST_PREFIX,
    fetch_tiles,
    store_tile_manifest,
    tiles_covering,
)
from fcc_coverage import (
    GRAND_CANYON_LON_LAT,
    PHASE_A_PROVIDER_ID,
    CellSource,
    FccCell,
    WrongFccFile,
    coverage_prefix,
    extract_gpkg,
    flag_points_covered,
    point_to_cell,
    read_fcc_cells,
    release_of,
    write_cells_parquet,
)
from lake_write import (
    contract_columns,
    delete_partitions_before,
    replace_rows_since,
    spark_schema,
    write_frame_partition,
    write_run_partition,
)
from ookla_tiles import (
    Quarter,
    arizona_tile_rows,
    download_quarter,
    newest_published_quarter,
    quarter_prefix,
    store_quarter_manifest,
)
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
from report_copy import (
    cell_day_rows,
    copy_marker,
    mark_copied,
    read_reports_to_copy,
    report_rows,
    set_aside_reasons,
    set_aside_rows,
)
from sample_iceberg_job import CATALOG_NAME
from satellite_windows import (
    MAX_WINDOW_ROWS,
    SatelliteElements,
    WindowRun,
    enforce_row_limit,
    run_window_job,
)
from terrain_horizon import RANGE_M, HorizonProfile, compute_horizons, validate_horizon
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
# Lake copies of reports are deleted 30 days after their copy (ADR 0034).
REPORT_COPY_RETENTION = timedelta(days=30)
# A day's reports can be copied on later nights; 20 days of recount covers many missed nights.
CELL_DAY_RECOUNT_DAYS = 20


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
    if page_hashes == _loaded_hashes(spark, f"{CATALOG_NAME}.{namespace}.nps_trail_line"):
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


def load_coverage_if_changed(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    now_utc: datetime,
    work_dir: Path,
) -> dict:
    """Load the newest kept FCC file and flag the newest trail points, if either changed (C6).

    The FCC site refuses automated requests, so the file is put in the raw bucket by hand and this
    step never downloads it. Coverage is reference data (ADR 0028): it runs when the kept file's
    hash is not the loaded one, or the trail points are newer than the flags. Returns
    ``{"changed": False}``, or how many cells and points were used and how many are covered.
    """
    points_table = f"{CATALOG_NAME}.{namespace}.trail_point"
    points_date = _newest_run_date(spark, points_table)
    if points_date is None:
        raise ValueError("no trail points are loaded yet, so there is nothing to flag")
    manifest = latest_manifest(s3, raw_bucket, coverage_prefix())
    if manifest is None:
        raise ValueError(f"no FCC file is kept under {coverage_prefix()}")
    flags_date = _newest_run_date(spark, f"{CATALOG_NAME}.{namespace}.trail_point_coverage")
    loaded = _loaded_hashes(spark, f"{CATALOG_NAME}.{namespace}.fcc_coverage_cell")
    if manifest["content_sha256"] in loaded and flags_date and flags_date >= points_date:
        return {"changed": False}

    body = read_raw(s3, raw_bucket, manifest["raw_key"])
    if hashlib.sha256(body).hexdigest() != manifest["content_sha256"]:
        raise WrongFccFile(f"{manifest['raw_key']}: the hash differs from its manifest")
    gpkg = extract_gpkg(body, work_dir)
    source = CellSource(
        release=release_of(manifest["raw_key"]),
        source_url=manifest["source_url"],
        fetched_at_utc=datetime.fromisoformat(manifest["fetched_at_utc"]),
        content_sha256=manifest["content_sha256"],
        run_date=run_date,
    )

    def cells() -> Iterator[FccCell]:
        return read_fcc_cells(
            gpkg, provider_id=PHASE_A_PROVIDER_ID, must_contain=GRAND_CANYON_LON_LAT
        )

    parquet = Path(work_dir) / "fcc_coverage_cell.parquet"
    summary = write_cells_parquet(cells(), parquet, source)
    contract = Path(contracts_dir) / "fcc_mobile_coverage.yaml"
    schema = spark_schema(contract_columns(contract, "fcc_coverage_cell"))
    frame = spark.read.schema(schema).parquet(parquet.as_uri())
    write_frame_partition(spark, "fcc_coverage_cell", frame, namespace=namespace)

    points = _trail_points(spark, points_table, points_date)
    wanted = {point_to_cell(point.lat, point.lon) for point in points}
    listed = {cell.h3_cell_res9 for cell in cells() if cell.h3_cell_res9 in wanted}
    flags = flag_points_covered(points, listed, summary["carrier"], point_to_cell)
    origin = {
        "technology": summary["technology"],
        "release": source.release,
        "content_sha256": source.content_sha256,
    }
    write_run_partition(
        spark,
        "trail_point_coverage",
        [flag | origin for flag in flags],
        run_date,
        columns=contract_columns(
            Path(contracts_dir) / "trail_point_coverage.yaml", "trail_point_coverage"
        ),
        namespace=namespace,
    )
    return {
        "changed": True,
        "cells": summary["cells"],
        "points": len(points),
        "covered": sum(flag["covered"] for flag in flags),
    }


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


def compute_windows(
    spark,  # noqa: ANN001, a pyspark SparkSession
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    span_start_utc: datetime,
    run_started_utc: datetime,
    now_utc: datetime,
    max_rows: int = MAX_WINDOW_ROWS,
) -> dict:
    """Write the run date's satellite windows for every trail point (C5).

    The satellites are the run date's ``dtc_satellite`` selection. The points and their horizons
    are the newest partitions, because both are reference data (ADR 0028); horizons older than
    the points would belong to points that are gone, so they stop the step. The windows are
    built and counted inside Spark, and a count over ``max_rows`` stops the step before anything
    is written (OQ-1). Returns how many satellites, points and windows there were.
    """
    satellites = _dtc_satellites(spark, f"{CATALOG_NAME}.{namespace}.dtc_satellite", run_date)
    points_table = f"{CATALOG_NAME}.{namespace}.trail_point"
    horizon_table = f"{CATALOG_NAME}.{namespace}.trail_point_horizon"
    points_date = _newest_run_date(spark, points_table)
    if points_date is None:
        raise ValueError("no trail points are loaded yet, so there is nowhere to find windows for")
    horizon_date = _newest_run_date(spark, horizon_table)
    if horizon_date is None:
        raise ValueError("no terrain horizons are computed yet; compute_horizons runs first")
    if horizon_date < points_date:
        raise ValueError(
            f"the newest horizons ({horizon_date}) are older than the newest trail points "
            f"({points_date}); compute_horizons must run for the new points first"
        )

    run = WindowRun(
        run_date=run_date,
        span_start_utc=span_start_utc,
        run_started_utc=run_started_utc,
        loaded_at_utc=now_utc,
    )
    points = _trail_points(spark, points_table, points_date)
    columns = contract_columns(Path(contracts_dir) / "satellite_window.yaml", "satellite_window")
    frame = run_window_job(
        spark, run, satellites, points, _horizons(spark, horizon_table, horizon_date), columns
    )
    # Cached, so counting for the limit and writing do not compute every window twice.
    frame = frame.persist()
    try:
        enforce_row_limit(frame, max_rows)
        windows = frame.count()
        write_frame_partition(spark, "satellite_window", frame, namespace=namespace)
    finally:
        frame.unpersist()
    return {"satellites": len(satellites), "points": len(points), "windows": windows}


def copy_tables_for_dbt(
    spark,  # noqa: ANN001, a pyspark SparkSession
    run_date: date,
    *,
    namespace: str,
    input_dir: Path,
    run_time: datetime,
) -> dict:
    """Copy the partitions tonight's dbt models read to plain Parquet (C7, OQ-40).

    dbt on DuckDB does not read Iceberg. Trail points and their coverage flags are reference data,
    so their newest partitions count (ADR 0028); flags older than the points would belong to
    points that are gone, so they stop the step. The windows must be tonight's. Returns which
    partitions were copied and how many windows there are.

    The reports of the 7 days up to ``run_time`` are copied for the area counts (C23, ADR 0030).
    copy_reports runs first, so the report table exists even on a night with no reports.
    """
    points_table = f"{CATALOG_NAME}.{namespace}.trail_point"
    coverage_table = f"{CATALOG_NAME}.{namespace}.trail_point_coverage"
    windows_table = f"{CATALOG_NAME}.{namespace}.satellite_window"
    points_date = _newest_run_date(spark, points_table)
    if points_date is None:
        raise ValueError("no trail points are loaded yet, so dbt has nothing to build from")
    coverage_date = _newest_run_date(spark, coverage_table)
    if coverage_date is None:
        raise ValueError("no coverage flags are loaded yet; load_coverage runs first")
    if coverage_date < points_date:
        raise ValueError(
            f"the newest coverage flags ({coverage_date}) are older than the newest trail points "
            f"({points_date}); load_coverage must run for the new points first"
        )
    tonight = f"run_date = DATE '{run_date.isoformat()}'"
    query = f"SELECT COUNT(*) AS rows FROM {windows_table} WHERE {tonight}"
    windows = spark.sql(query).collect()[0]["rows"]
    if windows == 0:
        raise ValueError(f"no satellite windows for {run_date}; compute_windows runs first")
    reports_table = f"{CATALOG_NAME}.{namespace}.signal_report"
    if not spark.catalog.tableExists(reports_table):
        raise ValueError(f"{reports_table} does not exist; copy_reports runs first")

    # Spark's default time format has no time zone. This one stores the UTC instant itself.
    spark.conf.set("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
    copies = {
        "trail_point": (points_table, f"run_date = DATE '{points_date.isoformat()}'"),
        "trail_point_coverage": (coverage_table, f"run_date = DATE '{coverage_date.isoformat()}'"),
        "satellite_window": (windows_table, tonight),
    }
    queries = {
        name: f"SELECT * FROM {table} WHERE {partition}"
        for name, (table, partition) in copies.items()
    }
    queries["signal_report"] = _reports_query(reports_table, run_time)
    for name, query in queries.items():
        frame = spark.sql(query).coalesce(1)
        frame.write.mode("overwrite").parquet((Path(input_dir) / name).as_uri())
    return {
        "trail_point_date": points_date.isoformat(),
        "coverage_date": coverage_date.isoformat(),
        "windows": windows,
    }


REPORT_COUNT_DAYS = 7  # ADR 0030


def _reports_query(table: str, run_time: datetime) -> str:
    """Select the reports whose hour falls in the 7 days up to ``run_time``.

    Times are compared as epoch seconds, because the Spark sessions set no time zone.
    """
    end = require_utc(run_time, "run_time")
    start = end - timedelta(days=REPORT_COUNT_DAYS)
    hour = "unix_timestamp(report_hour_utc)"
    return (
        "SELECT report_id, h3_cell_res9, carrier, had_signal, report_hour_utc "
        f"FROM {table} WHERE {hour} > {int(start.timestamp())} "
        f"AND {hour} <= {int(end.timestamp())}"
    )


def _orbit_rows(s3, raw_bucket: str, manifest: dict, contract: Path) -> list[dict]:  # noqa: ANN001
    """Read the kept CelesTrak file, check it against the contract, and shape its rows."""
    records = parse_gp_records(read_raw(s3, raw_bucket, manifest["raw_key"]), contract)
    return lake_rows(records, manifest, contract)


def _loaded_hashes(spark, table: str) -> set[str]:  # noqa: ANN001
    """Return the source file hashes in the table's newest partition, or none."""
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


def _dtc_satellites(spark, table: str, run_date: date) -> list[SatelliteElements]:  # noqa: ANN001
    """Return the run date's selected satellites, or stop if there are none."""
    names = [field.name for field in fields(SatelliteElements)]
    plain = date(run_date.year, run_date.month, run_date.day)
    query = (
        f"SELECT {', '.join(names)} FROM {table} "
        f"WHERE run_date = DATE '{plain.isoformat()}' ORDER BY norad_cat_id"
    )
    rows = spark.sql(query).collect() if spark.catalog.tableExists(table) else []
    if not rows:
        raise ValueError(f"dtc_satellite has no satellites for {plain}; select_dtc runs first")
    return [SatelliteElements.from_row(row) for row in rows]


def _horizons(spark, table: str, run_date: date) -> dict[str, HorizonProfile]:  # noqa: ANN001
    """Return one partition's horizons by trail point."""
    query = (
        f"SELECT trail_point_id, horizon_angles_deg FROM {table} "
        f"WHERE run_date = DATE '{run_date.isoformat()}'"
    )
    return {
        row["trail_point_id"]: HorizonProfile(
            row["trail_point_id"], tuple(float(a) for a in row["horizon_angles_deg"])
        )
        for row in spark.sql(query).collect()
    }


def copy_reports(
    spark,  # noqa: ANN001, a pyspark SparkSession
    dynamodb,  # noqa: ANN001, a boto3 DynamoDB client
    reports_table: str,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    run_time: datetime,
) -> dict:
    """Copy the hiker reports to the lake, set aside the flagged ones, and recount the days (C23).

    Order matters (ADR 0012): the lake writes come first, and only then is each report marked
    copied with its 30-day expiry, so a failed night loses nothing. Lake partitions older than
    30 days are then deleted (ADR 0034), and the last 20 days of ``report_cell_day`` are counted
    again, because a day's reports can arrive over the next nights.
    """
    contracts = Path(contracts_dir)
    run_time = require_utc(run_time, "run_time")
    marker = copy_marker(run_time)
    reports = read_reports_to_copy(dynamodb, reports_table, marker)

    points_table = f"{CATALOG_NAME}.{namespace}.trail_point"
    newest = _newest_run_date(spark, points_table)
    if newest is None:
        raise ValueError("trail_point has no rows; load_trails runs first")
    points = [(point.lat, point.lon) for point in _trail_points(spark, points_table, newest)]
    reasons = set_aside_reasons(reports, points)
    kept = [report for report in reports if report.report_id not in reasons]

    for table, rows in (
        ("signal_report", report_rows(kept, run_time)),
        ("signal_report_set_aside", set_aside_rows(reports, reasons)),
    ):
        write_run_partition(
            spark,
            table,
            rows,
            run_date,
            columns=contract_columns(contracts / f"{table}.yaml", table),
            namespace=namespace,
            allow_empty=True,
        )
    expires = int((run_time + REPORT_COPY_RETENTION).timestamp())
    marked = mark_copied(dynamodb, reports_table, [r.report_id for r in reports], marker, expires)

    for table in ("signal_report", "signal_report_set_aside"):
        delete_partitions_before(
            spark, table, run_date - REPORT_COPY_RETENTION, namespace=namespace
        )
    first_day = run_date - timedelta(days=CELL_DAY_RECOUNT_DAYS)
    counts = cell_day_rows(
        _kept_reports_since(spark, f"{CATALOG_NAME}.{namespace}.signal_report", first_day),
        run_time,
        first_day,
    )
    replace_rows_since(
        spark,
        "report_cell_day",
        counts,
        run_date,
        columns=contract_columns(contracts / "report_cell_day.yaml", "report_cell_day"),
        namespace=namespace,
        date_column="report_date_utc",
        first_date=first_day,
    )
    return {
        "copied": len(reports),
        "set_aside": len(reasons),
        "marked": marked,
        "cell_days": len(counts),
    }


def ookla_quarter_to_load(
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    run_date: date,
    *,
    opener: Callable = urllib.request.urlopen,
) -> Quarter | None:
    """Return Ookla's newest published quarter if it is not loaded yet, else None (C13).

    A quarter counts as loaded once its manifest is kept, so most nights this is one header
    request and one listing, with no Spark.
    """
    quarter = newest_published_quarter(run_date, opener=opener)
    if latest_manifest(s3, raw_bucket, quarter_prefix(quarter)) is not None:
        return None
    return quarter


def load_ookla_quarter(
    spark,  # noqa: ANN001, a pyspark SparkSession
    s3,  # noqa: ANN001, a boto3 S3 client
    raw_bucket: str,
    quarter: Quarter,
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    now_utc: datetime,
    work_dir: Path,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """Load one quarter's Arizona tiles into ``ookla_tile``, then keep its manifest (C13).

    The manifest is what marks the quarter loaded, so it is kept only after the lake write: a
    night that fails part way loads the quarter again. The worldwide file is deleted afterwards.
    Returns the quarter and how many tiles and tests were loaded.
    """
    path, manifest = download_quarter(quarter, work_dir, now_utc=now_utc, opener=opener)
    try:
        rows = arizona_tile_rows(path, manifest)
    finally:
        path.unlink()
    write_run_partition(
        spark,
        "ookla_tile",
        rows,
        run_date,
        columns=contract_columns(Path(contracts_dir) / "ookla_open_data.yaml", "ookla_tile"),
        namespace=namespace,
    )
    store_quarter_manifest(s3, raw_bucket, manifest)
    return {
        "changed": True,
        "quarter": quarter.label,
        "tiles": len(rows),
        "tests": sum(row["test_count"] for row in rows),
    }


def _kept_reports_since(spark, table: str, first_day: date) -> list[dict]:  # noqa: ANN001
    """Return the copied reports from ``first_day`` on, with their hours as aware UTC times.

    The hour is read as epoch seconds, which do not depend on the Spark session's time zone.
    """
    if not spark.catalog.tableExists(table):
        return []
    first = int(datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC).timestamp())
    query = (
        "SELECT h3_cell_res9, had_signal, unix_timestamp(report_hour_utc) AS hour_epoch "
        f"FROM {table} WHERE report_hour_utc >= timestamp_seconds({first})"
    )
    return [
        {
            "h3_cell_res9": row["h3_cell_res9"],
            "had_signal": row["had_signal"],
            "report_hour_utc": datetime.fromtimestamp(row["hour_epoch"], tz=UTC),
        }
        for row in spark.sql(query).collect()
    ]
