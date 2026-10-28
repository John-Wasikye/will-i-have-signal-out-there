"""Trail loader (C3): Grand Canyon's Phase A trails as lines, and a point every 50 meters.

Steps, each a function so a task can run them in order:

1. ``fetch_trail_pages`` asks the NPS Public Trails service for one park, in OBJECTID order,
   2,000 records a page, until the service no longer says the transfer limit was exceeded.
   Any status other than 200, an error inside a 200, or too many pages stops the pull.
2. ``store_trail_pages`` keeps each page unchanged with a manifest (engineering standard 1).
3. ``parse_trail_geojson`` checks the page's fields against the contract (C8), then reads each
   feature as a ``TrailLine``.
4. ``select_trails`` keeps the Phase A trails (ADR 0020) by their whole ``TRLNAME``, because
   other trails contain the same words (OQ-36). Each must be exactly one line in one part;
   anything else stops the run, since joining segments is a design decision, not a guess.
5. ``trail_point_rows`` places a point every 50 m along each line, measured along the line,
   and keeps the line's last point so both ends of the trail are on the map.
6. ``load_trail_tables`` writes ``nps_trail_line`` and ``trail_point`` for the run date.

Trail IDs are readable slugs such as ``grca-bright-angel``, not the service's OBJECTID, which
can change when the NPS republishes. Elevation is added by the terrain step (C4).
"""

from __future__ import annotations

import json
import math
import re
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlencode

from contract_diff import (
    assert_no_breaking_change,
    diff_schema,
    load_contract,
    observed_schema_from_records,
)
from lake_write import write_run_partition
from raw_store import FetchRefused, RawFile, download, write_raw
from timeutil import format_utc

NPS_TRAILS_QUERY_URL = (
    "https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/"
    "NPS_Public_Trails/FeatureServer/0/query"
)
PHASE_A_UNIT_CODE = "GRCA"
PHASE_A_TRAILS = ("Bright Angel", "South Kaibab", "North Kaibab")
PAGE_SIZE = 2000
MAX_PAGES = 10
POINT_SPACING_M = 50.0
EARTH_MEAN_RADIUS_M = 6_371_008.8
RAW_PREFIX = "signal/nps/trails"

Coordinate = tuple[float, float]


@dataclass(frozen=True)
class TrailLine:
    """One trail feature from the service. ``parts`` holds each run of (lon, lat) points."""

    trail_line_id: str
    trlname: str | None
    unitcode: str
    parts: tuple[tuple[Coordinate, ...], ...]


@dataclass(frozen=True)
class TrailPoint:
    """One sampled point; ``seq`` counts from 0 at the trail's first point."""

    point_id: str
    trail_id: str
    trail_name: str
    unit_code: str
    seq: int
    lon: float
    lat: float


def trail_query_url(unit_code: str, offset: int) -> str:
    """Return the query URL for one page of a park's trails."""
    if not re.fullmatch(r"[A-Z]{4}", unit_code):
        raise ValueError(f"{unit_code!r} is not a four-letter NPS unit code")
    query = {
        "where": f"UNITCODE='{unit_code}'",
        "outFields": "*",
        "orderByFields": "OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "f": "geojson",
    }
    return f"{NPS_TRAILS_QUERY_URL}?{urlencode(query)}"


def fetch_trail_pages(
    unit_code: str,
    *,
    now_utc: datetime,
    opener: Callable = urllib.request.urlopen,
    max_pages: int = MAX_PAGES,
) -> list[RawFile]:
    """Download every page of a park's trails, all stamped with the same fetch time."""
    pages: list[RawFile] = []
    offset = 0
    while True:
        if len(pages) == max_pages:
            raise FetchRefused(f"{unit_code}: more than {max_pages} pages; check the query")
        page = download(trail_query_url(unit_code, offset), now_utc=now_utc, opener=opener)
        payload = json.loads(page.body)
        if "error" in payload:
            raise FetchRefused(f"{unit_code}: the service returned an error: {payload['error']}")
        pages.append(page)
        if not _transfer_limit_exceeded(payload):
            return pages
        offset += len(payload["features"])


def _transfer_limit_exceeded(payload: Mapping) -> bool:
    # ArcGIS puts the flag at the top level of GeoJSON, or under "properties" in some versions.
    return bool(
        payload.get("exceededTransferLimit")
        or payload.get("properties", {}).get("exceededTransferLimit")
    )


def store_trail_pages(client, bucket: str, pages: Sequence[RawFile]) -> list[dict]:  # noqa: ANN001
    """Write each page unchanged with its manifest, and return the manifests in page order.

    ``client`` is a boto3 S3 client. Every page of one pull shares a fetch time and a folder.
    """
    manifests = []
    for number, page in enumerate(pages):
        unit_code = _unit_code_from(page.url)
        folder = f"{RAW_PREFIX}/unitcode={unit_code}/fetched_at={format_utc(page.fetched_at)}"
        stem = f"{folder}/page-{number:03d}"
        manifests.append(write_raw(client, bucket, f"{stem}.json", f"{stem}.manifest.json", page))
    return manifests


def _unit_code_from(url: str) -> str:
    match = re.search(r"UNITCODE%3D%27([A-Z]{4})%27", url)
    if not match:
        raise ValueError(f"no unit code in {url}")
    return match.group(1)


def parse_trail_geojson(body: bytes, contract_path: Path) -> list[TrailLine]:
    """Read one page as trail lines, after checking its fields against the contract."""
    features = json.loads(body)["features"]
    properties = [feature["properties"] for feature in features]
    if properties:
        observed = observed_schema_from_records(properties)
        assert_no_breaking_change(diff_schema(load_contract(contract_path), observed), "nps_trails")
    return [_trail_line(feature) for feature in features]


def _trail_line(feature: Mapping) -> TrailLine:
    geometry = feature["geometry"]
    if geometry["type"] == "LineString":
        parts = [geometry["coordinates"]]
    elif geometry["type"] == "MultiLineString":
        parts = geometry["coordinates"]
    else:
        raise ValueError(f"OBJECTID {feature['properties']['OBJECTID']}: {geometry['type']}")
    return TrailLine(
        trail_line_id=str(feature["properties"]["OBJECTID"]),
        trlname=feature["properties"]["TRLNAME"],
        unitcode=feature["properties"]["UNITCODE"],
        parts=tuple(tuple((p[0], p[1]) for p in part) for part in parts),
    )


def select_trails(lines: Iterable[TrailLine], names: Sequence[str]) -> list[TrailLine]:
    """Return one line per name, in the order of ``names``, matching the whole name."""
    lines = list(lines)
    selected = []
    for name in names:
        matches = [line for line in lines if line.trlname == name]
        if len(matches) != 1:
            raise ValueError(f"{name}: found {len(matches)} lines; expected exactly 1 (OQ-36)")
        if len(matches[0].parts) != 1:
            raise ValueError(f"{name}: the line has {len(matches[0].parts)} parts; expected 1")
        selected.append(matches[0])
    return selected


def distance_m(a: Coordinate, b: Coordinate) -> float:
    """Return the great-circle distance in meters between two (lon, lat) points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_M * math.asin(math.sqrt(h))


def sample_points_along_line(line: Sequence[Coordinate], spacing_m: float) -> list[Coordinate]:
    """Place a point every ``spacing_m`` along the line, plus the line's last point.

    Distance is measured along the line, segment by segment. Within a segment a point is placed
    by straight interpolation of longitude and latitude, which is exact enough for segments of
    a few hundred meters.
    """
    if len(line) < 2:
        raise ValueError("a line needs at least two points")
    points = [line[0]]
    next_at = spacing_m
    walked = 0.0
    for start, end in zip(line, line[1:], strict=False):
        length = distance_m(start, end)
        while length > 0 and next_at <= walked + length:
            share = (next_at - walked) / length
            points.append(
                (start[0] + share * (end[0] - start[0]), start[1] + share * (end[1] - start[1]))
            )
            next_at += spacing_m
        walked += length
    if distance_m(points[-1], line[-1]) > 0.01:
        points.append(line[-1])
    return points


def trail_id_for(unit_code: str, name: str) -> str:
    """Return a readable, stable trail ID such as ``grca-bright-angel``."""
    words = re.findall(r"[a-z0-9]+", f"{unit_code} {name}".lower())
    return "-".join(words)


def trail_point_rows(lines: Iterable[TrailLine], spacing_m: float) -> list[TrailPoint]:
    """Sample each selected line and number its points from 0."""
    points = []
    for line in lines:
        trail_id = trail_id_for(line.unitcode, line.trlname)
        for seq, (lon, lat) in enumerate(sample_points_along_line(line.parts[0], spacing_m)):
            points.append(
                TrailPoint(
                    point_id=f"{trail_id}-{seq:05d}",
                    trail_id=trail_id,
                    trail_name=line.trlname,
                    unit_code=line.unitcode,
                    seq=seq,
                    lon=lon,
                    lat=lat,
                )
            )
    return points


def trail_line_rows(lines: Iterable[TrailLine], manifest: Mapping) -> list[dict]:
    """Shape the selected lines for ``nps_trail_line``, with the page's manifest columns."""
    fetched_at = datetime.strptime(manifest["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    return [
        {
            "trail_line_id": line.trail_line_id,
            "trlname": line.trlname,
            "unitcode": line.unitcode,
            "geometry_geojson": json.dumps(
                {"type": "LineString", "coordinates": [list(p) for p in line.parts[0]]}
            ),
            "source_url": manifest["source_url"],
            "fetched_at_utc": fetched_at.replace(tzinfo=UTC),
            "content_sha256": manifest["content_sha256"],
        }
        for line in lines
    ]


def load_trail_tables(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    line_rows: list[dict],
    point_rows: list[TrailPoint],
    run_date: date,
    *,
    namespace: str,
) -> dict[str, int]:
    """Write ``nps_trail_line`` and ``trail_point`` for the run date; return each row count."""
    return {
        "nps_trail_line": write_run_partition(
            spark, "nps_trail_line", line_rows, run_date, namespace=namespace
        ),
        "trail_point": write_run_partition(
            spark,
            "trail_point",
            [asdict(point) for point in point_rows],
            run_date,
            namespace=namespace,
        ),
    }
