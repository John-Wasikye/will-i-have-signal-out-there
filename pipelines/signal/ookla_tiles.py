"""Load Ookla's open mobile speed-test tiles for Arizona (C13 part 1, contract ookla_open_data).

Ookla publishes one worldwide Parquet file per quarter in its public bucket on AWS open data. The
archive is public and does not change, so the file goes to a work folder on the box and only a
manifest of URL, size and hash is kept in the raw bucket (engineering standard 1). The loader keeps
the tiles whose centre falls inside Arizona's bounding box and gives each the H3 resolution 8 cell
of that centre (engineering standard 9). Ookla already keeps only tests with GPS-quality
locations, so there is no accuracy filter (OQ-10).
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import h3
import pyarrow.compute as pc
import pyarrow.parquet as pq
from raw_store import FETCH_TIMEOUT_SECONDS, FetchRefused
from timeutil import format_utc, require_utc

OOKLA_BASE_URL = (
    "https://ookla-open-data.s3.us-west-2.amazonaws.com/parquet/performance/type=mobile"
)
MANIFEST_PREFIX = "signal/ookla/manifest"
# West, south, east, north. Tiles of neighbouring states inside the box are kept: they are still
# measured evidence near the border, and the box is how the contract cuts the worldwide file.
ARIZONA_BOX = (-114.82, 31.33, -109.04, 37.00)
H3_RESOLUTION = 8
SOURCE_COLUMNS = (
    "quadkey",
    "tile_x",
    "tile_y",
    "avg_d_kbps",
    "avg_u_kbps",
    "avg_lat_ms",
    "tests",
    "devices",
)
# The worldwide file is about 190 MB, so it is read and written in pieces, never whole in memory.
CHUNK_BYTES = 8 * 1024 * 1024
BATCH_ROWS = 200_000


class OoklaNotPublished(RuntimeError):
    """Neither of the last two quarters is in Ookla's bucket."""


class WrongOoklaFile(ValueError):
    """The quarter's file lacks a field the contract relies on."""


@dataclass(frozen=True)
class Quarter:
    """One calendar quarter of Ookla's release."""

    year: int
    number: int

    @property
    def label(self) -> str:
        """The quarter as the lake stores it, for example ``2026-Q3``."""
        return f"{self.year}-Q{self.number}"

    @property
    def url(self) -> str:
        """The public URL of the quarter's worldwide file, named after its first day."""
        first_day = date(self.year, 3 * self.number - 2, 1)
        return (
            f"{OOKLA_BASE_URL}/year={self.year}/quarter={self.number}/"
            f"{first_day.isoformat()}_performance_mobile_tiles.parquet"
        )


def recent_quarters(run_date: date) -> list[Quarter]:
    """Return the two newest quarters that ended before ``run_date``, newest first."""
    current = (run_date.month - 1) // 3 + 1
    quarters = []
    year, number = run_date.year, current
    for _ in range(2):
        year, number = (year - 1, 4) if number == 1 else (year, number - 1)
        quarters.append(Quarter(year, number))
    return quarters


def newest_published_quarter(
    run_date: date, *, opener: Callable = urllib.request.urlopen
) -> Quarter:
    """Return the newest of the two recent quarters that Ookla has published.

    Ookla publishes a quarter some weeks after it ends, so the newest one may not be there yet.
    Only a 404 means "not published"; any other error stops the step.
    """
    for quarter in recent_quarters(run_date):
        request = urllib.request.Request(quarter.url, method="HEAD")
        try:
            with opener(request, timeout=FETCH_TIMEOUT_SECONDS):
                return quarter
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    raise OoklaNotPublished(f"Ookla has published neither quarter before {run_date}")


def download_quarter(
    quarter: Quarter,
    dest_dir: Path,
    *,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
) -> tuple[Path, dict]:
    """Download the quarter's file into ``dest_dir``; return its path and its manifest."""
    now_utc = require_utc(now_utc, "now_utc")
    path = Path(dest_dir) / quarter.url.rsplit("/", 1)[1]
    digest = hashlib.sha256()
    size = 0
    with opener(quarter.url, timeout=FETCH_TIMEOUT_SECONDS) as response, path.open("wb") as out:
        if response.status != 200:
            raise FetchRefused(f"{quarter.url} answered HTTP {response.status}")
        while chunk := response.read(CHUNK_BYTES):
            digest.update(chunk)
            out.write(chunk)
            size += len(chunk)
    if size == 0:
        raise FetchRefused(f"{quarter.url} returned an empty body")
    return path, {
        "quarter": quarter.label,
        "source_url": quarter.url,
        "fetched_at_utc": format_utc(now_utc),
        "size_bytes": size,
        "content_sha256": digest.hexdigest(),
    }


def arizona_tile_rows(path: Path, manifest: dict) -> list[dict]:
    """Return the ``ookla_tile`` rows of the tiles whose centre is inside Arizona's box."""
    source = pq.ParquetFile(path)
    missing = [name for name in SOURCE_COLUMNS if name not in source.schema_arrow.names]
    if missing:
        raise WrongOoklaFile(f"{manifest['source_url']} has no {', '.join(missing)}")
    fetched_at = datetime.fromisoformat(manifest["fetched_at_utc"])
    west, south, east, north = ARIZONA_BOX
    rows = []
    for batch in source.iter_batches(batch_size=BATCH_ROWS, columns=list(SOURCE_COLUMNS)):
        x, y = batch.column("tile_x"), batch.column("tile_y")
        inside = pc.and_(
            pc.and_(pc.greater_equal(x, west), pc.less_equal(x, east)),
            pc.and_(pc.greater_equal(y, south), pc.less_equal(y, north)),
        )
        for tile in batch.filter(inside).to_pylist():
            rows.append(
                {
                    "quarter": manifest["quarter"],
                    "tile_key": tile["quadkey"],
                    "h3_cell_res8": _h3_cell(tile["tile_y"], tile["tile_x"]),
                    "test_count": tile["tests"],
                    "device_count": tile["devices"],
                    "avg_download_kbps": tile["avg_d_kbps"],
                    "avg_upload_kbps": tile["avg_u_kbps"],
                    "avg_latency_ms": tile["avg_lat_ms"],
                    "source_url": manifest["source_url"],
                    "fetched_at_utc": fetched_at,
                    "content_sha256": manifest["content_sha256"],
                }
            )
    return rows


def _h3_cell(lat: float, lon: float) -> str:
    return h3.latlng_to_cell(lat, lon, H3_RESOLUTION)


def quarter_prefix(quarter: Quarter) -> str:
    """Return the raw bucket folder of the quarter's manifests."""
    return f"{MANIFEST_PREFIX}/quarter={quarter.label}/"


def store_quarter_manifest(client, bucket: str, manifest: dict) -> str:  # noqa: ANN001
    """Keep the manifest in the raw bucket, never replacing one, and return its key.

    ``client`` is a boto3 S3 client.
    """
    year, number = manifest["quarter"].split("-Q")
    prefix = quarter_prefix(Quarter(int(year), int(number)))
    key = f"{prefix}fetched_at={manifest['fetched_at_utc']}/manifest.json"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest, indent=2).encode(),
        IfNoneMatch="*",
        ContentType="application/json",
    )
    return key
