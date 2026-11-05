"""Trail API tests: /trails and /trails/{trail_id}/signal against published Parquet.

Every answer comes from the published files, so the API works with the box off (AC-1A.6).
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import trails
import yaml
from fastapi.testclient import TestClient

import app as serving_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI = REPO_ROOT / "docs" / "trip-planner" / "openapi.yaml"
SPAN_START = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
VALID_UNTIL = SPAN_START + timedelta(hours=26)
RUN_STARTED = datetime(2026, 11, 5, 10, 1, tzinfo=UTC)
UTC_US = pa.timestamp("us", tz="UTC")


def _write_published(folder: Path) -> None:
    pq.write_table(
        pa.table(
            {
                "trail_point_id": ["ba-00001", "ba-00000", "sk-00000"],
                "trail_id": ["grca-bright-angel", "grca-bright-angel", "grca-south-kaibab"],
                "trail_name": ["Bright Angel", "Bright Angel", "South Kaibab"],
                "unit_code": ["GRCA", "GRCA", "GRCA"],
                "seq": pa.array([1, 0, 0], pa.int32()),
                "lon": [-112.1, -112.2, -112.3],
                "lat": [36.1, 36.2, 36.3],
                "h3_cell_res9": ["a", "b", "c"],
            }
        ),
        folder / "dim_trail_point.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "trail_point_id": ["ba-00000", "ba-00001", "sk-00000"],
                "carrier": ["T-Mobile"] * 3,
                "covered": [True, False, True],
                "fcc_release": ["D25"] * 3,
            }
        ),
        folder / "fct_trail_point_coverage.parquet",
    )
    starts = [SPAN_START + timedelta(minutes=m) for m in (40, 5, 0)]
    ends = [SPAN_START + timedelta(minutes=m) for m in (50, 8, 9)]
    pq.write_table(
        pa.table(
            {
                "trail_point_id": ["ba-00000", "ba-00000", "sk-00000"],
                "period_start_utc": pa.array(starts, UTC_US),
                "period_end_utc": pa.array(ends, UTC_US),
                "min_elevation_deg": [10.0] * 3,
                "run_logical_date": pa.array([date(2026, 11, 5)] * 3, pa.date32()),
                "valid_until_utc": pa.array([VALID_UNTIL] * 3, UTC_US),
                "run_started_utc": pa.array([RUN_STARTED] * 3, UTC_US),
            }
        ),
        folder / "fct_reachable_period.parquet",
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    _write_published(tmp_path)
    monkeypatch.setattr(trails, "PUBLISHED_DIR", tmp_path)
    return TestClient(serving_app.app)


@pytest.fixture
def signal(client) -> dict:
    return client.get("/trails/grca-bright-angel/signal").json()


def test_trails_lists_each_trail_once_by_name(client):
    response = client.get("/trails")
    assert response.status_code == 200
    assert response.json() == {
        "trails": [
            {"trail_id": "grca-bright-angel", "trail_name": "Bright Angel", "unit_code": "GRCA"},
            {"trail_id": "grca-south-kaibab", "trail_name": "South Kaibab", "unit_code": "GRCA"},
        ]
    }


def test_signal_carries_the_run_stamps_the_page_shows(signal):
    assert signal["trail_id"] == "grca-bright-angel"
    assert signal["run_logical_date"] == "2026-11-05"
    assert signal["valid_until_utc"] == "2026-11-06T12:00:00Z"
    assert signal["last_good_run_utc"] == "2026-11-05T10:01:00Z"
    assert signal["min_elevation_deg"] == 10.0
    assert signal["carriers"] == ["T-Mobile"]


def test_signal_returns_the_trails_points_in_order(signal):
    assert [point["seq"] for point in signal["points"]] == [0, 1]
    assert [point["trail_point_id"] for point in signal["points"]] == ["ba-00000", "ba-00001"]
    assert signal["points"][0]["lon"] == -112.2
    assert signal["points"][0]["lat"] == 36.2


def test_each_point_has_its_coverage_flag(signal):
    assert signal["points"][0]["coverage"] == [{"carrier": "T-Mobile", "covered": True}]
    assert signal["points"][1]["coverage"] == [{"carrier": "T-Mobile", "covered": False}]


def test_each_point_has_its_reachable_periods_in_time_order(signal):
    assert signal["points"][0]["windows"] == [
        {"start_utc": "2026-11-05T10:05:00Z", "end_utc": "2026-11-05T10:08:00Z"},
        {"start_utc": "2026-11-05T10:40:00Z", "end_utc": "2026-11-05T10:50:00Z"},
    ]


def test_a_point_with_no_reachable_period_has_an_empty_list(signal):
    assert signal["points"][1]["windows"] == []


def test_another_trails_points_stay_out_of_the_answer(signal):
    assert "sk-00000" not in {point["trail_point_id"] for point in signal["points"]}


def test_an_unknown_trail_answers_404_with_the_error_code(client):
    response = client.get("/trails/grca-nowhere/signal")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "trail_not_found"


def test_a_trail_id_cannot_reach_the_sql(client):
    response = client.get("/trails/x' OR '1'='1/signal")
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/trails", "/trails/grca-bright-angel/signal"])
def test_missing_published_files_answer_503_with_the_error_code(path, tmp_path, monkeypatch):
    monkeypatch.setattr(trails, "PUBLISHED_DIR", tmp_path / "nothing-here")
    response = TestClient(serving_app.app).get(path)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "data_unavailable"


def test_the_contract_describes_a_window_without_a_satellite():
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    window = contract["components"]["schemas"]["WindowOut"]
    assert window["required"] == ["start_utc", "end_utc"]
    assert set(window["properties"]) == {"start_utc", "end_utc"}


def test_an_answer_has_every_field_the_contract_requires(signal):
    schemas = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]
    assert set(schemas["TrailSignal"]["required"]) <= set(signal)
    assert set(schemas["PointSignal"]["required"]) <= set(signal["points"][0])
