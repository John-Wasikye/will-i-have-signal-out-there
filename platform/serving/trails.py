"""Trail routes of the serving API (C11): /trails and /trails/{trail_id}/signal.

The contract is docs/trip-planner/openapi.yaml. Every answer comes from the published Parquet
files, so a request works with the session box switched off (AC-1A.6). A point's windows are
reachable periods: overlapping satellite windows merged by dbt, because every window of a trail
would not fit in one answer. Values from a request go in query parameters only.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
from duckdb_query import query_rows
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PUBLISHED_DIR = Path(os.environ.get("PUBLISHED_DIR", "published"))

RELEASE_PATTERN = re.compile(r"(?P<half>[JD])(?P<year>\d{2})(?:_\w+)?")

router = APIRouter(tags=["trails"])


class TrailSummary(BaseModel):
    """One trail the page can show."""

    trail_id: str
    trail_name: str | None
    unit_code: str


class TrailList(BaseModel):
    """Answer from GET /trails."""

    trails: list[TrailSummary]


class CarrierCoverage(BaseModel):
    """One carrier's FCC claim at one point. A modeled claim, not a measurement."""

    carrier: str
    covered: bool


class WindowOut(BaseModel):
    """One period when at least one satellite is reachable."""

    start_utc: datetime
    end_utc: datetime


class PointSignal(BaseModel):
    """One sampled point of a trail."""

    trail_point_id: str
    seq: int
    lon: float
    lat: float
    coverage: list[CarrierCoverage]
    windows: list[WindowOut]


class CoverageSource(BaseModel):
    """The FCC release behind one carrier's coverage on a trail, and the date it is as of."""

    carrier: str
    fcc_release: str
    data_as_of: date


class TrailSignal(BaseModel):
    """Answer from GET /trails/{trail_id}/signal."""

    trail_id: str
    run_logical_date: date
    valid_until_utc: datetime
    last_good_run_utc: datetime
    min_elevation_deg: float
    carriers: list[str]
    coverage_sources: list[CoverageSource]
    points: list[PointSignal]


def _table(name: str) -> str:
    return str(PUBLISHED_DIR / f"{name}.parquet")


def _utc(microseconds: int) -> datetime:
    """Convert epoch microseconds (epoch_us in SQL) to an aware UTC datetime.

    DuckDB returns the number directly, so no timezone library is needed in Lambda.
    """
    return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)


def release_data_date(release: str) -> date:
    """Return the date an FCC release's data is as of.

    A release looks like J26 or J26_10nov2026: the letter is J for the June release and D for
    the December release, the two digits are the data year, and an optional suffix after the
    underscore is the date the file was published, which does not change the data date.
    """
    match = RELEASE_PATTERN.fullmatch(release)
    if match is None:
        raise ValueError(f"Unknown FCC release {release!r}: expected J or D, two digits of year.")
    year = 2000 + int(match["year"])
    return date(year, 6, 30) if match["half"] == "J" else date(year, 12, 31)


def _error(status: int, code: str, message: str) -> JSONResponse:
    """Build the error body from design doc section 10."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _unavailable() -> JSONResponse:
    return _error(503, "data_unavailable", "Published data cannot be read.")


def _coverage_by_point(trail_id: str) -> dict[str, list[CarrierCoverage]]:
    rows = query_rows(
        "SELECT c.trail_point_id, c.carrier, c.covered "
        "FROM read_parquet(?) AS c JOIN read_parquet(?) AS p USING (trail_point_id) "
        "WHERE p.trail_id = ? ORDER BY c.carrier",
        [_table("fct_trail_point_coverage"), _table("dim_trail_point"), trail_id],
    )
    coverage: dict[str, list[CarrierCoverage]] = defaultdict(list)
    for row in rows:
        coverage[row["trail_point_id"]].append(
            CarrierCoverage(carrier=row["carrier"], covered=row["covered"])
        )
    return coverage


def _coverage_sources(trail_id: str) -> list[CoverageSource]:
    """One source per carrier: its oldest release, because the map is only as fresh as that.

    A carrier with a release this code cannot read gets no source, since its oldest date is then
    unknown; the date is a detail and must never break the trail answer.
    """
    rows = query_rows(
        "SELECT DISTINCT c.carrier, c.fcc_release "
        "FROM read_parquet(?) AS c JOIN read_parquet(?) AS p USING (trail_point_id) "
        "WHERE p.trail_id = ?",
        [_table("fct_trail_point_coverage"), _table("dim_trail_point"), trail_id],
    )
    unreadable = {
        row["carrier"] for row in rows if RELEASE_PATTERN.fullmatch(row["fcc_release"]) is None
    }
    oldest: dict[str, CoverageSource] = {}
    for row in rows:
        if row["carrier"] in unreadable:
            continue
        source = CoverageSource(
            carrier=row["carrier"],
            fcc_release=row["fcc_release"],
            data_as_of=release_data_date(row["fcc_release"]),
        )
        kept = oldest.get(source.carrier)
        if kept is None or (source.data_as_of, source.fcc_release) < (
            kept.data_as_of,
            kept.fcc_release,
        ):
            oldest[source.carrier] = source
    return [oldest[carrier] for carrier in sorted(oldest)]


def _windows_by_point(trail_id: str) -> dict[str, list[WindowOut]]:
    rows = query_rows(
        "SELECT r.trail_point_id, epoch_us(r.period_start_utc) AS start_us, "
        "epoch_us(r.period_end_utc) AS end_us "
        "FROM read_parquet(?) AS r JOIN read_parquet(?) AS p USING (trail_point_id) "
        "WHERE p.trail_id = ? ORDER BY r.period_start_utc",
        [_table("fct_reachable_period"), _table("dim_trail_point"), trail_id],
    )
    windows: dict[str, list[WindowOut]] = defaultdict(list)
    for row in rows:
        windows[row["trail_point_id"]].append(
            WindowOut(start_utc=_utc(row["start_us"]), end_utc=_utc(row["end_us"]))
        )
    return windows


@router.get(
    "/trails",
    response_model=TrailList,
    responses={503: {"description": "Published data is missing or cannot be read."}},
)
def list_trails() -> TrailList | JSONResponse:
    """List the trails in the published data, by name."""
    try:
        rows = query_rows(
            "SELECT DISTINCT trail_id, trail_name, unit_code FROM read_parquet(?) "
            "ORDER BY trail_name, trail_id",
            [_table("dim_trail_point")],
        )
    except duckdb.Error:
        return _unavailable()
    return TrailList(trails=[TrailSummary(**row) for row in rows])


@router.get(
    "/trails/{trail_id}/signal",
    response_model=TrailSignal,
    responses={
        404: {"description": "No trail has this ID."},
        503: {"description": "Published data is missing or cannot be read."},
    },
)
def get_trail_signal(trail_id: str) -> TrailSignal | JSONResponse:
    """Return every point of one trail with its coverage flags and reachable periods."""
    try:
        points = query_rows(
            "SELECT trail_point_id, seq, lon, lat FROM read_parquet(?) "
            "WHERE trail_id = ? ORDER BY seq",
            [_table("dim_trail_point"), trail_id],
        )
        if not points:
            return _error(404, "trail_not_found", "No trail has this ID.")
        (run,) = query_rows(
            "SELECT CAST(MAX(run_logical_date) AS VARCHAR) AS run_logical_date, "
            "epoch_us(MAX(valid_until_utc)) AS valid_until_us, "
            "epoch_us(MAX(run_started_utc)) AS run_started_us, "
            "MAX(min_elevation_deg) AS min_elevation_deg FROM read_parquet(?)",
            [_table("fct_reachable_period")],
        )
        coverage = _coverage_by_point(trail_id)
        windows = _windows_by_point(trail_id)
        coverage_sources = _coverage_sources(trail_id)
    except duckdb.Error:
        return _unavailable()

    return TrailSignal(
        trail_id=trail_id,
        run_logical_date=date.fromisoformat(run["run_logical_date"]),
        valid_until_utc=_utc(run["valid_until_us"]),
        last_good_run_utc=_utc(run["run_started_us"]),
        min_elevation_deg=run["min_elevation_deg"],
        carriers=sorted({item.carrier for flags in coverage.values() for item in flags}),
        coverage_sources=coverage_sources,
        points=[
            PointSignal(
                **point,
                coverage=coverage.get(point["trail_point_id"], []),
                windows=windows.get(point["trail_point_id"], []),
            )
            for point in points
        ],
    )
