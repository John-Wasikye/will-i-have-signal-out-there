"""Read the FCC mobile coverage cells and mark each trail point covered or not (C6).

The FCC publishes one GeoPackage per provider, state and technology. A GeoPackage is a SQLite
file, so the standard library reads it. Each H3 resolution 9 cell appears once. Every listed cell
counts as covered, whatever its environment or signal value (OQ-44); those two values are kept on
the cell so the rule can change later without loading the file again.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from trail_loader import TrailPoint


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
