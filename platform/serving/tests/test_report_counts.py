"""Report count API tests: GET /report-counts against published Parquet (C23 part 2).

An area is the H3 resolution 6 parent of a report's cell (ADR 0030). The API finds a trail's
areas from the cells of its published points, so it needs no H3 library in Lambda.
"""

from datetime import UTC, datetime
from pathlib import Path

import h3
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import report_counts
import trails
import yaml
from duckdb_query import query_rows
from fastapi.testclient import TestClient

import app as serving_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI = REPO_ROOT / "docs" / "trip-planner" / "openapi.yaml"
COUNTED_THROUGH = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
UTC_US = pa.timestamp("us", tz="UTC")

# Bright Angel starts in START_AREA and ends in END_AREA. South Kaibab sits in a third area.
START_CELL = h3.latlng_to_cell(36.40, -111.80, 9)
END_CELL = h3.latlng_to_cell(36.06, -112.14, 9)
OTHER_CELL = h3.latlng_to_cell(36.70, -111.50, 9)
START_AREA, END_AREA, OTHER_AREA = (
    h3.cell_to_parent(c, 6) for c in (START_CELL, END_CELL, OTHER_CELL)
)


def _write_published(folder: Path) -> None:
    pq.write_table(
        pa.table(
            {
                "trail_point_id": ["ba-00001", "ba-00000", "ba-00002", "sk-00000"],
                "trail_id": ["grca-bright-angel"] * 3 + ["grca-south-kaibab"],
                "seq": pa.array([1, 0, 2, 0], pa.int32()),
                "h3_cell_res9": [START_CELL, START_CELL, END_CELL, OTHER_CELL],
            }
        ),
        folder / "dim_trail_point.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "area_id": [END_AREA, END_AREA, START_AREA, OTHER_AREA],
                "carrier": ["T-Mobile", "Verizon", "T-Mobile", "AT&T"],
                "had_signal": [True, False, False, True],
                "report_count": pa.array([4, 2, 5, 6], pa.int32()),
                "counted_through_utc": pa.array([COUNTED_THROUGH] * 4, UTC_US),
            }
        ),
        folder / "fct_report_counts_area.parquet",
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    _write_published(tmp_path)
    monkeypatch.setattr(report_counts, "PUBLISHED_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trails, "PUBLISHED_DIR", tmp_path)
    return TestClient(serving_app.app)


def _counts(client, query: str = "") -> list[tuple]:
    response = client.get(f"/report-counts{query}")
    assert response.status_code == 200
    return [
        (c["area_id"], c["carrier"], c["had_signal"], c["report_count"])
        for c in response.json()["counts"]
    ]


@pytest.mark.parametrize("resolution", [0, 5, 6, 8])
def test_the_sql_parent_cell_matches_the_h3_library(resolution):
    cells = [
        h3.latlng_to_cell(lat, lon, 9)
        for lat, lon in [(36.1, -112.1), (-33.9, 151.2), (64.1, -21.9)]
    ]
    parent = report_counts.h3_parent_sql("cell", resolution)
    sql = f"SELECT {parent} AS parent FROM (SELECT unnest(?) AS cell)"
    rows = query_rows(sql, [cells])
    assert [row["parent"] for row in rows] == [h3.cell_to_parent(c, resolution) for c in cells]


def test_a_trail_gets_the_counts_of_the_areas_its_points_sit_in_from_its_start(client):
    assert _counts(client, "?trail_id=grca-bright-angel") == [
        (START_AREA, "T-Mobile", False, 5),
        (END_AREA, "T-Mobile", True, 4),
        (END_AREA, "Verizon", False, 2),
    ]


def test_without_a_trail_every_published_count_is_returned(client):
    assert len(_counts(client)) == 4


def test_an_unknown_trail_has_no_counts(client):
    assert _counts(client, "?trail_id=no-such-trail") == []


def test_a_trail_id_cannot_reach_the_sql(client):
    assert _counts(client, "?trail_id=x' OR '1'='1") == []


def test_missing_published_files_answer_503_with_the_error_code(tmp_path, monkeypatch):
    monkeypatch.setattr(report_counts, "PUBLISHED_DIR", tmp_path / "nothing-here", raising=False)
    response = TestClient(serving_app.app).get("/report-counts?trail_id=grca-bright-angel")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "data_unavailable"


def test_an_answer_has_every_field_the_contract_requires(client):
    schemas = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]
    (count, *_) = client.get("/report-counts").json()["counts"]
    assert set(schemas["ReportCount"]["required"]) <= set(count)
