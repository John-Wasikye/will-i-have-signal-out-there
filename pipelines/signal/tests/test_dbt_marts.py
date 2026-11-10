"""Tests for the dbt project (C7): a real ``dbt build`` on small Parquet tables.

dbt lives in its own Python environment because Airflow's pinned packages refuse it, so these
tests run it the way the box does, as a separate program. They skip when that environment is
not there. CI installs it from platform/box/requirements-dbt.txt.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import h3
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from dbt_runner import DbtBuildFailed, run_dbt

REPO = Path(__file__).parents[3]
PROJECT = REPO / "pipelines" / "signal" / "dbt"
CONTRACTS = REPO / "docs" / "trip-planner" / "contracts"
DBT = next(
    (
        path
        for path in (
            REPO / ".venv-dbt" / "Scripts" / "dbt.exe",
            REPO / ".venv-dbt" / "bin" / "dbt",
        )
        if path.exists()
    ),
    None,
)
pytestmark = pytest.mark.skipif(DBT is None, reason="the dbt environment .venv-dbt is not here")

RUN_DATE = date(2026, 11, 4)
SPAN_START = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
VALID_UNTIL = SPAN_START + timedelta(hours=26)
RUN_STARTED = datetime(2026, 11, 4, 10, 1, tzinfo=UTC)
LOADED_AT = datetime(2026, 11, 4, 10, 2, tzinfo=UTC)
UTC_US = pa.timestamp("us", tz="UTC")

POINTS = [
    {
        "trail_point_id": f"grca-bright-angel-0000{n}",
        "trail_id": "grca-bright-angel",
        "trail_name": "Bright Angel",
        "unit_code": "GRCA",
        "seq": n,
        "lon": -112.14,
        "lat": 36.05 + n / 1000,
        "run_date": date(2026, 10, 30),
    }
    for n in range(2)
]
COVERAGE_BASE = {
    "carrier": "T-Mobile",
    "release": "J25",
    "content_sha256": "a" * 64,
    "run_date": RUN_DATE,
}
COVERAGE = [
    {
        **COVERAGE_BASE,
        "trail_point_id": "grca-bright-angel-00000",
        "technology": "4G LTE",
        "h3_cell_res9": "8929a000000ffff",
        "covered": True,
    },
    {
        **COVERAGE_BASE,
        "trail_point_id": "grca-bright-angel-00000",
        "technology": "5G NR",
        "h3_cell_res9": "8929a000000ffff",
        "covered": False,
    },
    {
        **COVERAGE_BASE,
        "trail_point_id": "grca-bright-angel-00001",
        "technology": "4G LTE",
        "h3_cell_res9": "8929a000001ffff",
        "covered": False,
    },
]
WINDOW = {
    "trail_point_id": "grca-bright-angel-00000",
    "satellite_id": "58705",
    "window_start_utc": SPAN_START + timedelta(minutes=5),
    "window_end_utc": SPAN_START + timedelta(minutes=8),
    "min_elevation_deg": 10.0,
    "valid_until_utc": VALID_UNTIL,
    "run_started_utc": RUN_STARTED,
    "loaded_at_utc": LOADED_AT,
    "run_date": RUN_DATE,
}
POINT_SCHEMA = pa.schema(
    [
        ("trail_point_id", pa.string()),
        ("trail_id", pa.string()),
        ("trail_name", pa.string()),
        ("unit_code", pa.string()),
        ("seq", pa.int32()),
        ("lon", pa.float64()),
        ("lat", pa.float64()),
        ("run_date", pa.date32()),
    ]
)
COVERAGE_SCHEMA = pa.schema(
    [
        ("trail_point_id", pa.string()),
        ("carrier", pa.string()),
        ("technology", pa.string()),
        ("h3_cell_res9", pa.string()),
        ("covered", pa.bool_()),
        ("release", pa.string()),
        ("content_sha256", pa.string()),
        ("run_date", pa.date32()),
    ]
)
WINDOW_SCHEMA = pa.schema(
    [
        ("trail_point_id", pa.string()),
        ("satellite_id", pa.string()),
        ("window_start_utc", UTC_US),
        ("window_end_utc", UTC_US),
        ("min_elevation_deg", pa.float64()),
        ("valid_until_utc", UTC_US),
        ("run_started_utc", UTC_US),
        ("loaded_at_utc", UTC_US),
        ("run_date", pa.date32()),
    ]
)

REPORT_SCHEMA = pa.schema(
    [
        ("report_id", pa.string()),
        ("h3_cell_res9", pa.string()),
        ("carrier", pa.string()),
        ("had_signal", pa.bool_()),
        ("report_hour_utc", UTC_US),
    ]
)
# Two H3 resolution 6 areas near Bright Angel: AREA holds three resolution 9 cells.
AREA = h3.cell_to_parent(h3.latlng_to_cell(36.06, -112.14, 9), 6)
AREA_CELLS = sorted(h3.cell_to_children(AREA, 9))[:3]
OTHER_AREA_CELL = h3.latlng_to_cell(36.40, -111.80, 9)


def _write(input_dir: Path, table: str, rows: list[dict], schema: pa.Schema) -> None:
    folder = input_dir / table
    folder.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), folder / "part-0.parquet")


def _build(tmp_path: Path, windows: list[dict], reports: list[dict] | None = None) -> Path:
    input_dir, output_dir = tmp_path / "input", tmp_path / "marts"
    _write(input_dir, "trail_point", POINTS, POINT_SCHEMA)
    _write(input_dir, "trail_point_coverage", COVERAGE, COVERAGE_SCHEMA)
    _write(input_dir, "satellite_window", windows, WINDOW_SCHEMA)
    _write(input_dir, "signal_report", reports or [], REPORT_SCHEMA)
    run_dbt(
        dbt_bin=DBT,
        project_dir=PROJECT,
        input_dir=input_dir,
        output_dir=output_dir,
        work_dir=tmp_path / "work",
        loaded_at_utc=LOADED_AT,
    )
    return output_dir


@pytest.fixture(scope="module")
def marts(tmp_path_factory) -> Path:
    return _build(tmp_path_factory.mktemp("dbt"), [WINDOW])


def _rows(marts: Path, name: str) -> list[dict]:
    return pq.read_table(marts / f"{name}.parquet").to_pylist()


@pytest.mark.parametrize(
    "mart",
    [
        "dim_trail_point",
        "dim_time",
        "fct_trail_point_coverage",
        "fct_satellite_window",
        "fct_reachable_period",
        "fct_report_counts_area",
    ],
)
def test_each_mart_has_exactly_its_contract_columns(marts, mart):
    contract = yaml.safe_load((CONTRACTS / f"{mart}.yaml").read_text(encoding="utf-8"))
    expected = {column["name"] for column in contract["schema"][0]["properties"]}
    assert set(pq.read_schema(marts / f"{mart}.parquet").names) == expected


def test_satellite_window_fact_renames_the_partition_to_the_run_logical_date(marts):
    (row,) = _rows(marts, "fct_satellite_window")
    assert row["run_logical_date"] == RUN_DATE
    assert row["window_start_utc"] == WINDOW["window_start_utc"]
    assert row["valid_until_utc"] == VALID_UNTIL


def _window(point: int, satellite: str, start: int, end: int) -> dict:
    return {
        **WINDOW,
        "trail_point_id": f"grca-bright-angel-0000{point}",
        "satellite_id": satellite,
        "window_start_utc": SPAN_START + timedelta(minutes=start),
        "window_end_utc": SPAN_START + timedelta(minutes=end),
    }


def _periods(tmp_path: Path, windows: list[dict]) -> list[tuple]:
    rows = _rows(_build(tmp_path, windows), "fct_reachable_period")
    minute = timedelta(minutes=1)
    return sorted(
        (
            row["trail_point_id"][-1],
            (row["period_start_utc"] - SPAN_START) // minute,
            (row["period_end_utc"] - SPAN_START) // minute,
        )
        for row in rows
    )


def test_overlapping_windows_become_one_period(tmp_path):
    windows = [_window(0, "1", 5, 8), _window(0, "2", 7, 12)]
    assert _periods(tmp_path, windows) == [("0", 5, 12)]


def test_a_window_inside_another_does_not_end_the_period_early(tmp_path):
    windows = [_window(0, "1", 5, 20), _window(0, "2", 7, 9), _window(0, "3", 18, 25)]
    assert _periods(tmp_path, windows) == [("0", 5, 25)]


def test_windows_in_neighboring_minutes_become_one_period(tmp_path):
    windows = [_window(0, "1", 5, 8), _window(0, "2", 9, 12)]
    assert _periods(tmp_path, windows) == [("0", 5, 12)]


def test_a_minute_with_no_satellite_splits_the_periods(tmp_path):
    windows = [_window(0, "1", 5, 8), _window(0, "2", 10, 12)]
    assert _periods(tmp_path, windows) == [("0", 5, 8), ("0", 10, 12)]


def test_each_point_has_its_own_periods(tmp_path):
    windows = [_window(0, "1", 5, 8), _window(1, "1", 7, 12)]
    assert _periods(tmp_path, windows) == [("0", 5, 8), ("1", 7, 12)]


def test_a_period_carries_the_run_stamps_the_page_shows(marts):
    (row,) = _rows(marts, "fct_reachable_period")
    assert row["valid_until_utc"] == VALID_UNTIL
    assert row["run_started_utc"] == RUN_STARTED
    assert row["run_logical_date"] == RUN_DATE
    assert row["min_elevation_deg"] == 10.0


def test_time_dimension_has_one_row_for_each_minute_of_the_26_hour_span(marts):
    rows = sorted(_rows(marts, "dim_time"), key=lambda row: row["time_utc"])
    assert len(rows) == 26 * 60
    assert rows[0]["time_utc"] == SPAN_START
    assert rows[-1]["time_utc"] == VALID_UNTIL - timedelta(minutes=1)
    assert rows[0]["time_key"] == "20261104T1000Z"


def test_coverage_fact_has_one_row_per_point_and_carrier_covered_by_any_technology(marts):
    rows = {row["trail_point_id"]: row for row in _rows(marts, "fct_trail_point_coverage")}
    assert len(_rows(marts, "fct_trail_point_coverage")) == 2
    assert rows["grca-bright-angel-00000"]["covered"] is True
    assert rows["grca-bright-angel-00001"]["covered"] is False
    assert rows["grca-bright-angel-00000"]["fcc_release"] == "J25"
    assert rows["grca-bright-angel-00000"]["loaded_at_utc"] == LOADED_AT


def test_trail_point_dimension_carries_the_cell_each_point_sits_in(marts):
    rows = {row["trail_point_id"]: row for row in _rows(marts, "dim_trail_point")}
    assert len(rows) == 2
    assert rows["grca-bright-angel-00001"]["h3_cell_res9"] == "8929a000001ffff"
    assert rows["grca-bright-angel-00001"]["seq"] == 1


def test_a_repeated_window_key_fails_the_build(tmp_path):
    with pytest.raises(DbtBuildFailed, match="fct_satellite_window"):
        _build(tmp_path, [WINDOW, WINDOW])


def test_a_window_that_ends_before_it_starts_fails_the_build(tmp_path):
    backwards = {**WINDOW, "window_end_utc": WINDOW["window_start_utc"] - timedelta(minutes=1)}
    with pytest.raises(DbtBuildFailed, match="fct_satellite_window"):
        _build(tmp_path, [backwards])


def test_a_window_on_an_unknown_trail_point_fails_the_build(tmp_path):
    stray = {**WINDOW, "trail_point_id": "grca-nowhere-00000"}
    with pytest.raises(DbtBuildFailed, match="fct_satellite_window"):
        _build(tmp_path, [stray])


def test_dbt_sends_nothing_home():
    project = yaml.safe_load((PROJECT / "dbt_project.yml").read_text(encoding="utf-8"))
    assert project["flags"]["send_anonymous_usage_stats"] is False
    assert project["flags"]["version_check"] is False


def _report(n: int, cell: str, carrier: str, had_signal: bool, hours_before: int) -> dict:
    return {
        "report_id": f"r{n}",
        "h3_cell_res9": cell,
        "carrier": carrier,
        "had_signal": had_signal,
        "report_hour_utc": SPAN_START - timedelta(hours=hours_before),
    }


AREA_REPORTS = [
    _report(1, AREA_CELLS[0], "T-Mobile", True, 30),
    _report(2, AREA_CELLS[1], "T-Mobile", True, 20),
    _report(3, AREA_CELLS[2], "T-Mobile", True, 10),
    _report(4, AREA_CELLS[0], "T-Mobile", False, 5),
    _report(5, AREA_CELLS[1], "Verizon", True, 2),
]
# Four reports in the other area: under the minimum of 5 (ADR 0030).
OTHER_REPORTS = [_report(10 + n, OTHER_AREA_CELL, "AT&T", True, n) for n in range(4)]


def _counts(tmp_path: Path, reports: list[dict]) -> list[dict]:
    return _rows(_build(tmp_path, [WINDOW], reports), "fct_report_counts_area")


def test_an_area_is_the_resolution_6_parent_of_the_report_cell(tmp_path):
    assert AREA != h3.cell_to_parent(OTHER_AREA_CELL, 6)
    rows = _counts(tmp_path, AREA_REPORTS)
    assert {row["area_id"] for row in rows} == {AREA}


def test_an_area_counts_its_reports_by_carrier_and_answer(tmp_path):
    rows = _counts(tmp_path, AREA_REPORTS)
    assert sorted((r["carrier"], r["had_signal"], r["report_count"]) for r in rows) == [
        ("T-Mobile", False, 1),
        ("T-Mobile", True, 3),
        ("Verizon", True, 1),
    ]


def test_an_area_with_fewer_than_5_reports_is_left_out(tmp_path):
    rows = _counts(tmp_path, AREA_REPORTS + OTHER_REPORTS)
    assert {row["area_id"] for row in rows} == {AREA}


def test_each_row_of_an_area_carries_the_areas_latest_report_hour(tmp_path):
    rows = _counts(tmp_path, AREA_REPORTS)
    latest = SPAN_START - timedelta(hours=2)
    assert {row["counted_through_utc"] for row in rows} == {latest}


def test_no_reports_give_no_counts_only_dbts_empty_placeholder_row(marts):
    # dbt-duckdb writes an empty model as one row of nulls, so the file keeps its columns.
    # The publisher drops that row (trail_publish.read_marts).
    rows = _rows(marts, "fct_report_counts_area")
    assert all(value is None for row in rows for value in row.values())
