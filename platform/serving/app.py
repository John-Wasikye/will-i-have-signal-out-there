"""Serving template: FastAPI app with /health and the sample route.

The contract is docs/platform/openapi-serving-template.yaml. Every answer is read
from published Parquet, never from the session box. A row older than its
freshness target is marked late, and its data is still returned (the page shows
a late notice).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from duckdb_query import query_rows
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

PUBLISHED_DIR = Path(os.environ.get("PUBLISHED_DIR", "published"))
SAMPLE_TABLE = PUBLISHED_DIR / "sample_answer.parquet"

app = FastAPI(
    title="Serving template (platform)",
    version="0.1.0",
    description=(
        "The first request after a period of inactivity may take up to 10 seconds "
        "while the service initializes."
    ),
)


class Health(BaseModel):
    """Answer from GET /health."""

    status: str
    generated_at_utc: datetime


class SampleAnswer(BaseModel):
    """One published row, with its late flag."""

    key: str
    value: str
    last_good_run_utc: datetime
    late: bool


def _from_epoch_microseconds(microseconds: int) -> datetime:
    """Convert epoch microseconds (from epoch_us in SQL) to an aware UTC datetime.

    DuckDB returns the number directly, so no timezone library is needed in Lambda.
    """
    return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)


def _is_late(last_good_run_utc: datetime, freshness_target_hours: float, now: datetime) -> bool:
    """Return True when the last good run is older than the freshness target."""
    age_hours = (now - last_good_run_utc).total_seconds() / 3600
    return age_hours > freshness_target_hours


@app.get("/health", response_model=Health, tags=["platform"])
def get_health() -> Health:
    """Report that the published data can be read. Reads no key."""
    try:
        query_rows("SELECT 1 FROM read_parquet(?) LIMIT 1", [str(SAMPLE_TABLE)])
    except Exception as error:  # noqa: BLE001, any read failure means unhealthy
        raise HTTPException(status_code=500, detail="Published data cannot be read.") from error
    return Health(status="ok", generated_at_utc=datetime.now(UTC))


@app.get(
    "/sample",
    response_model=SampleAnswer,
    responses={404: {"description": "No sample row with that key."}},
    tags=["platform"],
)
def get_sample(
    key: Annotated[str | None, Query(max_length=64)] = None,
) -> SampleAnswer:
    """Return one sample row. Without a key, return the first row by key."""
    select = (
        "SELECT key, value, epoch_us(last_good_run_utc) AS last_good_us, "
        "freshness_target_hours FROM read_parquet(?)"
    )
    if key is None:
        rows = query_rows(f"{select} ORDER BY key LIMIT 1", [str(SAMPLE_TABLE)])
    else:
        rows = query_rows(f"{select} WHERE key = ? LIMIT 1", [str(SAMPLE_TABLE), key])
    if not rows:
        raise HTTPException(status_code=404, detail="No sample row with that key.")

    row = rows[0]
    last_good = _from_epoch_microseconds(int(row["last_good_us"]))
    now = datetime.now(UTC)
    return SampleAnswer(
        key=row["key"],
        value=row["value"],
        last_good_run_utc=last_good,
        late=_is_late(last_good, float(row["freshness_target_hours"]), now),
    )
