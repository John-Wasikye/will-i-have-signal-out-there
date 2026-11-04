"""Fetch the Copernicus GLO-30 tiles the terrain horizon needs (C4, contract copernicus_glo30).

The tiles come from the public GLO-30 archive on AWS open data. The archive never changes, so the
tiles go to a work folder on the box and only a manifest of URL, size and hash is kept in the raw
bucket (engineering standard 1). The manifest's own hash goes on every horizon row, so a result
can be traced to the exact tiles it was built from.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from raw_store import download
from timeutil import format_utc
from trail_loader import EARTH_MEAN_RADIUS_M, TrailPoint

GLO30_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
MANIFEST_PREFIX = "signal/copernicus/manifest"
HEIGHT_DATUM = "EGM2008"
RESOLUTION_M = 30

Tile = tuple[int, int]  # (latitude, longitude) of the tile's south-west corner, whole degrees


class TileChanged(RuntimeError):
    """A tile's content differs from the last manifest, though the archive should never change."""


def tile_name(lat_floor: int, lon_floor: int) -> str:
    """Return the archive's name for the 1 by 1 degree tile with this south-west corner."""
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"


def tiles_covering(points: Sequence[TrailPoint], margin_m: float) -> list[Tile]:
    """Return every tile within ``margin_m`` of any point, sorted south to north, west to east."""
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    lat_margin = math.degrees(margin_m / EARTH_MEAN_RADIUS_M)
    # A degree of longitude is shortest at the highest latitude, so that latitude sets the margin.
    widest = max(abs(min(lats) - lat_margin), abs(max(lats) + lat_margin))
    lon_margin = lat_margin / math.cos(math.radians(widest))
    south, north = math.floor(min(lats) - lat_margin), math.floor(max(lats) + lat_margin)
    west, east = math.floor(min(lons) - lon_margin), math.floor(max(lons) + lon_margin)
    return [(lat, lon) for lat in range(south, north + 1) for lon in range(west, east + 1)]


def fetch_tiles(
    tiles: Sequence[Tile],
    dest_dir: Path,
    *,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
) -> list[dict]:
    """Download each tile into ``dest_dir`` and return its manifest row (the contract's columns)."""
    rows = []
    for lat, lon in tiles:
        name = tile_name(lat, lon)
        key = f"{name}/{name}.tif"
        raw = download(f"{GLO30_BASE_URL}/{key}", now_utc=now_utc, opener=opener)
        (Path(dest_dir) / f"{name}.tif").write_bytes(raw.body)
        rows.append(
            {
                "tile_key": key,
                "source_url": raw.url,
                "size_bytes": len(raw.body),
                "content_sha256": hashlib.sha256(raw.body).hexdigest(),
                "fetched_at_utc": format_utc(raw.fetched_at),
                "height_datum": HEIGHT_DATUM,
                "resolution_m": RESOLUTION_M,
            }
        )
    return rows


def store_tile_manifest(
    client,  # noqa: ANN001, a boto3 S3 client
    bucket: str,
    rows: Sequence[dict],
    *,
    previous: dict | None,
    fetched_at: datetime,
) -> dict:
    """Keep the manifest in the raw bucket and return its key and SHA-256 hash.

    ``previous`` is the last kept manifest, or None. A tile whose hash differs from it stops the
    run, because horizons from the old and the new tile would no longer agree.
    """
    known = {row["tile_key"]: row["content_sha256"] for row in (previous or {}).get("tiles", [])}
    for row in rows:
        if row["tile_key"] in known and known[row["tile_key"]] != row["content_sha256"]:
            raise TileChanged(f"{row['tile_key']} changed since the last manifest")
    body = json.dumps({"tiles": list(rows)}, indent=2).encode()
    key = f"{MANIFEST_PREFIX}/fetched_at={format_utc(fetched_at)}/manifest.json"
    client.put_object(
        Bucket=bucket, Key=key, Body=body, IfNoneMatch="*", ContentType="application/json"
    )
    return {"manifest_key": key, "manifest_sha256": hashlib.sha256(body).hexdigest()}
