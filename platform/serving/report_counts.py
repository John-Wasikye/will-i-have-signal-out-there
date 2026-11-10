"""Report count route of the serving API (C23 part 2): GET /report-counts.

The contract is docs/trip-planner/openapi.yaml. Counts come from the published file
fct_report_counts_area, which already leaves out any area with fewer than 5 reports in 7 days
(ADR 0030). An area is the H3 resolution 6 parent of a report's cell. A trail's areas are the
parents of its points' cells, worked out in SQL, so Lambda needs no H3 library. Values from a
request go in query parameters only.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from duckdb_query import query_rows
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PUBLISHED_DIR = Path(os.environ.get("PUBLISHED_DIR", "published"))
AREA_RESOLUTION = 6  # ADR 0030

router = APIRouter(tags=["reports"])


class ReportCount(BaseModel):
    """Hiker reports in one area for one carrier and answer, over the last 7 days."""

    area_id: str
    carrier: str
    had_signal: bool
    report_count: int


class ReportCounts(BaseModel):
    """Answer from GET /report-counts."""

    counts: list[ReportCount]


def h3_parent_sql(column: str, resolution: int) -> str:
    """Return SQL for the H3 cell that contains ``column``'s cell at ``resolution``.

    The same rule as the dbt macro h3_parent: an H3 index keeps its resolution in bits 52 to 55,
    and a parent has every finer 3-bit digit set to 7. ``column`` is a fixed name, never input.
    """
    finer_bits = 3 * (15 - resolution)
    return (
        f"lower(hex(((('0x' || {column})::UBIGINT & ~(15::UBIGINT << 52)) "
        f"| ({resolution}::UBIGINT << 52)) | ((1::UBIGINT << {finer_bits}) - 1)))"
    )


def _table(name: str) -> str:
    return str(PUBLISHED_DIR / f"{name}.parquet")


def _unavailable() -> JSONResponse:
    body = {"error": {"code": "data_unavailable", "message": "Published data cannot be read."}}
    return JSONResponse(status_code=503, content=body)


ALL_COUNTS = (
    "SELECT area_id, carrier, had_signal, report_count FROM read_parquet(?) "
    "ORDER BY area_id, carrier, had_signal DESC"
)
# A trail's areas, each with the first point of the trail that lies in it, so the counts
# come in order from the trail's start.
TRAIL_COUNTS = (
    "WITH trail_areas AS ("
    f"SELECT {h3_parent_sql('h3_cell_res9', AREA_RESOLUTION)} AS area_id, MIN(seq) AS first_seq "
    "FROM read_parquet(?) WHERE trail_id = ? GROUP BY 1) "
    "SELECT c.area_id, c.carrier, c.had_signal, c.report_count "
    "FROM read_parquet(?) AS c JOIN trail_areas AS t USING (area_id) "
    "ORDER BY t.first_seq, c.carrier, c.had_signal DESC"
)


@router.get(
    "/report-counts",
    response_model=ReportCounts,
    responses={503: {"description": "Published data is missing or cannot be read."}},
)
def get_report_counts(trail_id: str | None = None) -> ReportCounts | JSONResponse:
    """Return the published report counts, for one trail's areas when ``trail_id`` is given."""
    try:
        if trail_id is None:
            rows = query_rows(ALL_COUNTS, [_table("fct_report_counts_area")])
        else:
            rows = query_rows(
                TRAIL_COUNTS,
                [_table("dim_trail_point"), trail_id, _table("fct_report_counts_area")],
            )
    except duckdb.Error:
        return _unavailable()
    return ReportCounts(counts=[ReportCount(**row) for row in rows])
