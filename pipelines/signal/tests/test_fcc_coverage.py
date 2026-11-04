"""Tests for the FCC coverage loader (C6): read the hexagon cells from a provider's GeoPackage and
mark each trail point covered or not.

Every listed cell counts as covered, whatever its environment or signal value (OQ-44). No test
calls the FCC or AWS. A GeoPackage is a SQLite file, so each test builds a tiny real one.
"""

import sqlite3

import pytest
from fcc_coverage import FccCell, WrongFccFile, flag_points_covered, read_fcc_cells
from trail_loader import TrailPoint

T_MOBILE_ID = 130403
GRAND_CANYON = (-112.1, 36.1)


def _gpkg(path, rows, *, extent=(-114.8, 31.3, -109.0, 37.0)):
    """Write a GeoPackage with the FCC file's table layout and return its path."""
    connection = sqlite3.connect(path)
    connection.execute(
        "create table gpkg_contents (table_name text, data_type text, "
        "min_x real, min_y real, max_x real, max_y real)"
    )
    connection.execute("insert into gpkg_contents values ('bdc', 'features', ?, ?, ?, ?)", extent)
    connection.execute(
        "create table bdc (fid integer primary key, providerid integer, brandname text, "
        "technology integer, minsignal integer, environmnt integer, h3_res9_id text)"
    )
    connection.executemany(
        "insert into bdc (providerid, brandname, technology, minsignal, environmnt, h3_res9_id) "
        "values (?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()
    return path


def _read(path):
    return list(read_fcc_cells(path, provider_id=T_MOBILE_ID, must_contain=GRAND_CANYON))


def _point(point_id, lon=-112.1, lat=36.1):
    return TrailPoint(
        trail_point_id=point_id,
        trail_id="t1",
        trail_name="Bright Angel",
        unit_code="GRCA",
        seq=0,
        lon=lon,
        lat=lat,
    )


def test_reads_each_cell_with_its_environment_and_signal(tmp_path):
    path = _gpkg(
        tmp_path / "a.gpkg",
        [
            (T_MOBILE_ID, "T-Mobile", 400, -110, 0, "89269b4001bffff"),
            (T_MOBILE_ID, "T-Mobile", 400, -80, 1, "89269b4004bffff"),
        ],
    )
    assert _read(path) == [
        FccCell("89269b4001bffff", "T-Mobile", "400", 0, -110),
        FccCell("89269b4004bffff", "T-Mobile", "400", 1, -80),
    ]


def test_refuses_another_providers_file(tmp_path):
    path = _gpkg(tmp_path / "a.gpkg", [(999, "Other", 400, -100, 0, "89269b4001bffff")])
    with pytest.raises(WrongFccFile, match="provider"):
        _read(path)


def test_refuses_another_states_file(tmp_path):
    alabama = (-88.5, 30.1, -84.8, 35.1)
    path = _gpkg(
        tmp_path / "a.gpkg",
        [(T_MOBILE_ID, "T-Mobile", 400, -100, 0, "89269b4001bffff")],
        extent=alabama,
    )
    with pytest.raises(WrongFccFile, match="does not reach"):
        _read(path)


def test_refuses_a_file_with_no_cells(tmp_path):
    with pytest.raises(WrongFccFile, match="no cells"):
        _read(_gpkg(tmp_path / "a.gpkg", []))


def test_refuses_a_cell_listed_twice(tmp_path):
    row = (T_MOBILE_ID, "T-Mobile", 400, -100, 0, "89269b4001bffff")
    with pytest.raises(WrongFccFile, match="twice"):
        _read(_gpkg(tmp_path / "a.gpkg", [row, row]))


def test_a_point_in_a_listed_cell_is_covered_and_others_are_not():
    points = [_point("p1", lat=36.1), _point("p2", lat=36.2)]
    cells = {36.1: "cell-a", 36.2: "cell-b"}
    rows = flag_points_covered(points, {"cell-a"}, "T-Mobile", lambda lat, lon: cells[lat])
    assert [(row["trail_point_id"], row["covered"]) for row in rows] == [
        ("p1", True),
        ("p2", False),
    ]


def test_every_point_keeps_its_cell_and_carrier():
    rows = flag_points_covered([_point("p1")], set(), "T-Mobile", lambda lat, lon: "cell-a")
    assert rows == [
        {
            "trail_point_id": "p1",
            "carrier": "T-Mobile",
            "h3_cell_res9": "cell-a",
            "covered": False,
        }
    ]


def test_cell_lookup_gets_latitude_first():
    seen = []
    flag_points_covered(
        [_point("p1", lon=-112.0, lat=36.0)],
        set(),
        "T-Mobile",
        lambda lat, lon: seen.append((lat, lon)) or "cell-a",
    )
    assert seen == [(36.0, -112.0)]
