"""Read OpenCelliD cell locations for Arizona (C13 part 3, contract opencellid_towers).

OpenCelliD publishes one gzip CSV export per mobile country code (MCC). The download needs a
personal API token, so John downloads the files by hand and keeps them in the raw bucket with a
manifest; the token must never reach a manifest or the lake. The reader keeps the cells whose
estimated location falls inside Arizona's box, the same box as the Ookla tiles, and gives each the
H3 resolution 9 cell of that location (the FCC grain, ADR 0007). A row is a logical cell, not a
confirmed tower: several cells can share one tower.
"""

from __future__ import annotations

import gzip
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urlsplit

import h3
from ookla_tiles import ARIZONA_BOX

RAW_PREFIX = "signal/opencellid"
H3_RESOLUTION = 9
SOURCE_COLUMNS = (
    "radio",
    "mcc",
    "net",
    "area",
    "cell",
    "unit",
    "lon",
    "lat",
    "range",
    "samples",
    "changeable",
    "created",
    "updated",
    "averageSignal",
)


class WrongOpenCellidFile(ValueError):
    """The kept file or its manifest is not what the contract expects."""


def check_manifest(manifest: dict) -> None:
    """Stop if the manifest's URL has a query, where the download link carries the API token."""
    if urlsplit(manifest["source_url"]).query:
        raise WrongOpenCellidFile(
            f"{manifest['raw_key']}: the source URL has a query, which can hold the API token; "
            "keep the download page URL instead"
        )


def read_cell_lines(body: bytes) -> list[str]:
    """Return the text lines of a kept gzip CSV export, without line endings or blank lines."""
    return [line for line in gzip.decompress(body).decode("utf-8").splitlines() if line]


def arizona_cell_rows(lines: Iterable[str], manifest: dict) -> list[dict]:
    """Return the ``opencellid_tower`` rows of the cells inside Arizona's box.

    A header line, if the export has one, is skipped. Any line without the 14 source columns, or
    a cell listed twice, stops the read, because either means the format is not the one checked.
    """
    check_manifest(manifest)
    fetched_at = datetime.fromisoformat(manifest["fetched_at_utc"])
    west, south, east, north = ARIZONA_BOX
    rows: dict[str, dict] = {}
    for number, line in enumerate(lines, start=1):
        values = line.split(",")
        if len(values) != len(SOURCE_COLUMNS):
            raise WrongOpenCellidFile(
                f"{manifest['raw_key']} line {number}: {len(values)} values, "
                f"not the {len(SOURCE_COLUMNS)} columns of the export"
            )
        if tuple(values) == SOURCE_COLUMNS:
            continue
        cell = dict(zip(SOURCE_COLUMNS, values, strict=True))
        lon, lat = float(cell["lon"]), float(cell["lat"])
        if not (west <= lon <= east and south <= lat <= north):
            continue
        tower_id = "-".join(cell[name] for name in ("radio", "mcc", "net", "area", "cell"))
        if tower_id in rows:
            raise WrongOpenCellidFile(f"{manifest['raw_key']}: cell {tower_id} is listed twice")
        rows[tower_id] = {
            "tower_id": tower_id,
            "radio": cell["radio"],
            "mcc": int(cell["mcc"]),
            "net": int(cell["net"]),
            "area": int(cell["area"]),
            "cell": int(cell["cell"]),
            "lon": lon,
            "lat": lat,
            "range_m": int(cell["range"]),
            "samples": int(cell["samples"]),
            "created_utc": datetime.fromtimestamp(int(cell["created"]), tz=UTC),
            "updated_utc": datetime.fromtimestamp(int(cell["updated"]), tz=UTC),
            "h3_cell_res9": h3.latlng_to_cell(lat, lon, H3_RESOLUTION),
            "source_url": manifest["source_url"],
            "fetched_at_utc": fetched_at,
            "content_sha256": manifest["content_sha256"],
        }
    return list(rows.values())
