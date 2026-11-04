"""Tests for fetching the Copernicus GLO-30 tiles the horizon needs (C4, contract copernicus_glo30).

The archive never changes, so only a manifest of URL, size and hash is kept (engineering
standard 1); the tiles themselves go to a work folder on the box. No test calls the internet.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from elevation_source import (
    GLO30_BASE_URL,
    MANIFEST_PREFIX,
    TileChanged,
    fetch_tiles,
    store_tile_manifest,
    tile_name,
    tiles_covering,
)
from test_signal_nightly import FakeOpener, FakeS3
from trail_loader import TrailPoint

NOW = datetime(2026, 11, 3, 10, 5, tzinfo=UTC)


def point(lon: float, lat: float) -> TrailPoint:
    return TrailPoint("tp", "t", "Trail", "GRCA", 0, lon, lat)


# The three Phase A trailheads and Phantom Ranch span every Phase A trail.
PHASE_A_POINTS = [
    point(-112.1435, 36.0574),
    point(-112.0838, 36.0531),
    point(-112.0566, 36.2172),
    point(-112.0947, 36.1059),
]


def test_tile_names_follow_the_archive_layout():
    assert tile_name(36, -113) == "Copernicus_DSM_COG_10_N36_00_W113_00_DEM"
    assert tile_name(-1, 7) == "Copernicus_DSM_COG_10_S01_00_E007_00_DEM"


def test_the_phase_a_trails_need_the_four_tiles_the_first_run_check_found():
    # OQ-8: N35 and N36, W112 and W113 cover the trails plus the 15 km horizon range.
    assert tiles_covering(PHASE_A_POINTS, margin_m=16_000) == [
        (35, -113),
        (35, -112),
        (36, -113),
        (36, -112),
    ]


def test_a_small_margin_needs_only_the_tile_under_the_points():
    assert tiles_covering([point(-112.5, 36.5)], margin_m=1_000) == [(36, -113)]


def test_fetch_writes_each_tile_and_returns_its_manifest_row(tmp_path: Path):
    opener = FakeOpener(b"tile bytes")

    rows = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=opener)

    name = "Copernicus_DSM_COG_10_N36_00_W113_00_DEM"
    assert opener.urls == [f"{GLO30_BASE_URL}/{name}/{name}.tif"]
    assert (tmp_path / f"{name}.tif").read_bytes() == b"tile bytes"
    assert rows == [
        {
            "tile_key": f"{name}/{name}.tif",
            "source_url": f"{GLO30_BASE_URL}/{name}/{name}.tif",
            "size_bytes": 10,
            "content_sha256": hashlib.sha256(b"tile bytes").hexdigest(),
            "fetched_at_utc": "2026-11-03T10:05:00Z",
            "height_datum": "EGM2008",
            "resolution_m": 30,
        }
    ]


def test_the_manifest_rows_have_exactly_the_contract_columns(tmp_path: Path):
    contract = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
    from lake_write import contract_columns

    expected = [
        c.name for c in contract_columns(contract / "copernicus_glo30.yaml", "glo30_tile_manifest")
    ]
    rows = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"x"))

    assert list(rows[0]) == expected


def test_the_manifest_is_kept_once_and_its_hash_names_the_tile_set(tmp_path: Path):
    s3 = FakeS3()
    rows = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"x"))

    kept = store_tile_manifest(s3, "raw", rows, previous=None, fetched_at=NOW)

    key = f"{MANIFEST_PREFIX}/fetched_at=2026-11-03T10:05:00Z/manifest.json"
    assert kept["manifest_key"] == key
    assert json.loads(s3.objects[key]) == {"tiles": rows}
    assert kept["manifest_sha256"] == hashlib.sha256(s3.objects[key]).hexdigest()


def test_a_tile_whose_content_changed_stops_the_run(tmp_path: Path):
    # The archive is meant never to change. If a tile does, the horizons built from the old
    # one no longer match, so the run stops rather than mixing the two.
    old = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"old"))
    new = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"new"))

    with pytest.raises(TileChanged, match="N36_00_W113_00"):
        store_tile_manifest(FakeS3(), "raw", new, previous={"tiles": old}, fetched_at=NOW)


def test_a_previous_manifest_with_other_tiles_is_fine(tmp_path: Path):
    old = fetch_tiles([(35, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"old"))
    new = fetch_tiles([(36, -113)], tmp_path, now_utc=NOW, opener=FakeOpener(b"new"))

    kept = store_tile_manifest(FakeS3(), "raw", new, previous={"tiles": old}, fetched_at=NOW)

    assert kept["manifest_key"].endswith("manifest.json")
