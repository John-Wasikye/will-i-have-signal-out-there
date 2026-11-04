"""Read the FCC mobile coverage cells and mark each trail point covered or not (C6).

The FCC publishes one GeoPackage per provider, state and technology. A GeoPackage is a SQLite
file, so the standard library reads it. Each H3 resolution 9 cell appears once. Every listed cell
counts as covered, whatever its environment or signal value (OQ-44); those two values are kept on
the cell so the rule can change later without loading the file again.
"""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import h3
import pyarrow as pa
import pyarrow.parquet as pq
from trail_loader import TrailPoint

H3_RESOLUTION = 9
RAW_PREFIX = "signal/fcc/coverage"
PHASE_A_PROVIDER_ID = 130403  # T-Mobile (ADR 0020)
PHASE_A_STATE = "04"  # Arizona's FIPS code, as in the FCC file names
GRAND_CANYON_LON_LAT = (-112.1, 36.1)
PARQUET_BATCH_ROWS = 100_000

# The columns of fcc_coverage_cell in the contract's order, then the partition column.
CELL_FILE_SCHEMA = pa.schema(
    [
        ("h3_cell_res9", pa.string()),
        ("carrier", pa.string()),
        ("technology", pa.string()),
        ("release", pa.string()),
        ("environment", pa.int64()),
        ("min_signal_dbm", pa.int64()),
        ("source_url", pa.string()),
        ("fetched_at_utc", pa.timestamp("us", tz="UTC")),
        ("content_sha256", pa.string()),
        ("run_date", pa.date32()),
    ]
)


class WrongFccFile(RuntimeError):
    """The file is not the provider and state the run asked for, or its cells cannot be trusted."""


@dataclass(frozen=True)
class FccCell:
    """One listed H3 cell, with the values as the FCC file gives them."""

    h3_cell_res9: str
    carrier: str
    technology: str
    environment: int
    min_signal_dbm: int


@dataclass(frozen=True)
class CellSource:
    """Where a load's cells came from, as each row of ``fcc_coverage_cell`` records it."""

    release: str
    source_url: str
    fetched_at_utc: datetime
    content_sha256: str
    run_date: date


def coverage_prefix(provider_id: int = PHASE_A_PROVIDER_ID, state: str = PHASE_A_STATE) -> str:
    """Return the raw bucket folder that holds this provider's and state's kept files."""
    return f"{RAW_PREFIX}/providerid={provider_id}/state={state}/"


def release_of(raw_key: str) -> str:
    """Return the release in an FCC file name, such as ``D25_19oct2026`` (data date, file date)."""
    match = re.search(r"_(D\d{2}_\d{2}[a-z]{3}\d{4})\.zip$", raw_key)
    if match is None:
        raise WrongFccFile(f"{raw_key}: the file name has no release")
    return match.group(1)


def extract_gpkg(zip_body: bytes, work_dir: Path) -> Path:
    """Unzip the one GeoPackage in the FCC zip into ``work_dir`` and return its path."""
    with zipfile.ZipFile(io.BytesIO(zip_body)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".gpkg")]
        if len(names) != 1:
            raise WrongFccFile(f"expected one GeoPackage in the zip, found {names}")
        return Path(archive.extract(names[0], work_dir))


def write_cells_parquet(cells: Iterable[FccCell], path: Path, source: CellSource) -> dict:
    """Write the cells to a Parquet file for Spark, a batch at a time, and describe them.

    A state's cells are too many to pass through Airflow as Python rows, so they reach Spark as a
    file with declared types. Returns the file's ``carrier``, ``technology`` and ``cells`` count.
    """
    summary = {"cells": 0}
    batch: list[dict] = []
    with pq.ParquetWriter(path, CELL_FILE_SCHEMA) as writer:
        for cell in cells:
            summary.setdefault("carrier", cell.carrier)
            summary.setdefault("technology", cell.technology)
            summary["cells"] += 1
            batch.append(asdict(cell) | asdict(source))
            if len(batch) == PARQUET_BATCH_ROWS:
                writer.write_table(pa.Table.from_pylist(batch, schema=CELL_FILE_SCHEMA))
                batch = []
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=CELL_FILE_SCHEMA))
    return summary


def read_fcc_cells(
    path: Path, *, provider_id: int, must_contain: tuple[float, float]
) -> Iterator[FccCell]:
    """Check the file, then return its cells one at a time (a state holds about a million).

    ``must_contain`` is a (longitude, latitude) the file's extent has to reach. The FCC download
    page starts on Alabama, and a wrong state's file would otherwise mark every point uncovered.
    """
    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    table = _check_file(connection, path, provider_id, must_contain)
    return _cells(connection, table)


def _check_file(
    connection: sqlite3.Connection,
    path: Path,
    provider_id: int,
    must_contain: tuple[float, float],
) -> str:
    table, min_x, min_y, max_x, max_y = connection.execute(
        "select table_name, min_x, min_y, max_x, max_y from gpkg_contents"
    ).fetchone()
    lon, lat = must_contain
    if not (min_x <= lon <= max_x and min_y <= lat <= max_y):
        raise WrongFccFile(f"{path}: the file's extent does not reach {must_contain}")
    providers = [row[0] for row in connection.execute(f'select distinct providerid from "{table}"')]
    if not providers:
        raise WrongFccFile(f"{path}: the file has no cells")
    if providers != [provider_id]:
        raise WrongFccFile(f"{path}: expected provider {provider_id}, found {providers}")
    repeated = connection.execute(
        f'select h3_res9_id from "{table}" group by h3_res9_id having count(*) > 1 limit 1'
    ).fetchone()
    if repeated:
        raise WrongFccFile(f"{path}: cell {repeated[0]} is listed twice")
    return table


def _cells(connection: sqlite3.Connection, table: str) -> Iterator[FccCell]:
    rows = connection.execute(
        f'select h3_res9_id, brandname, technology, environmnt, minsignal from "{table}" '
        "order by fid"
    )
    for cell, carrier, technology, environment, min_signal in rows:
        yield FccCell(cell, carrier, str(technology), environment, min_signal)
    connection.close()


def flag_points_covered(
    points: Sequence[TrailPoint],
    covered_cells: Collection[str],
    carrier: str,
    cell_of: Callable[[float, float], str],
) -> list[dict]:
    """Return one row per point: its cell, and whether the carrier lists that cell.

    ``cell_of`` turns a latitude and longitude into the point's H3 resolution 9 cell.
    """
    rows = []
    for point in points:
        cell = cell_of(point.lat, point.lon)
        rows.append(
            {
                "trail_point_id": point.trail_point_id,
                "carrier": carrier,
                "h3_cell_res9": cell,
                "covered": cell in covered_cells,
            }
        )
    return rows


def point_to_cell(lat: float, lon: float) -> str:
    """Return the H3 cell at the resolution the FCC files use."""
    return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
