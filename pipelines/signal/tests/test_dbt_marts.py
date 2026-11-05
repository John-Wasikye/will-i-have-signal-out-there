"""Tests for the dbt project (C7): a real ``dbt build`` on small Parquet tables.

dbt lives in its own Python environment because Airflow's pinned packages refuse it, so these
tests run it the way the box does, as a separate program. They skip when that environment is
not there. CI installs it from platform/box/requirements-dbt.txt.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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


def _write(input_dir: Path, table: str, rows: list[dict], schema: pa.Schema) -> None:
    folder = input_dir / table
    folder.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), folder / "part-0.parquet")


def _build(tmp_path: Path, windows: list[dict]) -> Path:
    input_dir, output_dir = tmp_path / "input", tmp_path / "marts"
    _write(input_dir, "trail_point", POINTS, POINT_SCHEMA)
    _write(input_dir, "trail_point_coverage", COVERAGE, COVERAGE_SCHEMA)
    _write(input_dir, "satellite_window", windows, WINDOW_SCHEMA)
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
    "mart", ["dim_trail_point", "dim_time", "fct_trail_point_coverage", "fct_satellite_window"]
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
