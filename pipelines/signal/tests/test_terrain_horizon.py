"""Tests for the terrain horizon engine (C4): how high terrain rises in each compass direction
around a trail point, out to 15 km, as 36 angles (ADR 0004, defaults in ADR 0036).

Most tests use small made-up elevation grids. The AC-1A.2 test (canyon floor against rim) reads
the real Copernicus tiles and runs only where they are on this computer.
"""

import math
from pathlib import Path

import numpy as np
import pytest
from geotiff import ElevationGrid
from terrain_horizon import (
    EARTH_MEAN_RADIUS_M,
    EYE_HEIGHT_M,
    RANGE_M,
    SECTORS,
    STEP_M,
    ElevationTiles,
    HorizonProfile,
    MissingElevation,
    compute_horizon,
    horizon_at,
    load_elevation_tiles,
    max_elevation_angle,
    validate_horizon,
)
from trail_loader import TrailPoint

REAL_TILE_DIR = Path.home() / "AppData" / "Local" / "Temp" / "p1-checks" / "copernicus"
NO_REAL_TILES = "real Copernicus tiles are only on John's laptop"

# A made-up 0.4 by 0.4 degree area around the observer, cells of 0.001 degrees (about 90 m
# east-west and 111 m north-south at this latitude), wide enough for every 15 km ray.
WEST, NORTH, STEP_DEG, CELLS = -112.3, 36.3, 0.001, 401
OBSERVER_LON, OBSERVER_LAT = -112.1, 36.1
GROUND_M = 1000.0


def point(lon: float = OBSERVER_LON, lat: float = OBSERVER_LAT) -> TrailPoint:
    return TrailPoint(
        trail_point_id="tp-1",
        trail_id="t-1",
        trail_name="Test trail",
        unit_code="GRCA",
        seq=0,
        lon=lon,
        lat=lat,
    )


def cell_lon(col: int) -> float:
    return WEST + col * STEP_DEG


def cell_lat(row: int) -> float:
    return NORTH - row * STEP_DEG


def flat() -> np.ndarray:
    return np.full((CELLS, CELLS), GROUND_M, dtype=np.float32)


def tiles(heights: np.ndarray) -> ElevationTiles:
    return ElevationTiles([ElevationGrid(heights, west=WEST, north=NORTH, step_deg=STEP_DEG)])


def col_of(lon: float) -> int:
    return round((lon - WEST) / STEP_DEG)


def row_of(lat: float) -> int:
    return round((NORTH - lat) / STEP_DEG)


def test_defaults_are_the_ones_adr_0036_set() -> None:
    assert (RANGE_M, STEP_M, EYE_HEIGHT_M, SECTORS) == (15_000, 30, 1.7, 36)


def test_flat_ground_has_a_zero_horizon_all_round() -> None:
    horizon = compute_horizon(point(), tiles(flat()))

    assert horizon.trail_point_id == "tp-1"
    assert horizon.angles_deg == (0.0,) * 36


def test_a_wall_to_the_east_raises_only_the_east_sectors() -> None:
    heights = flat()
    # A block 300 m high, starting about 850 m east of the observer and about 1 km long north
    # to south, so rays to the north and south miss it.
    rows = slice(row_of(OBSERVER_LAT + 0.005), row_of(OBSERVER_LAT - 0.005) + 1)
    cols = slice(col_of(OBSERVER_LON + 0.0095), col_of(OBSERVER_LON + 0.02) + 1)
    heights[rows, cols] = GROUND_M + 300

    angles = compute_horizon(point(), tiles(heights)).angles_deg

    # First sample inside the wall is about 850 m away: atan(298 / 850) is about 19 degrees.
    assert 15 < angles[9] < 22
    assert angles[0] == 0.0  # north
    assert angles[18] == 0.0  # south
    assert angles[27] == 0.0  # west


def test_a_narrow_peak_off_the_sector_centre_still_counts() -> None:
    # One tall cell 2 km away at azimuth 94 degrees: inside sector 9 (85 to 95 degrees), but a
    # single ray down the sector centre (90 degrees) passes about 140 m from it. Rays every
    # degree across the sector catch it, so the horizon never misses a blocking peak.
    heights = flat()
    east_m, north_m = 2000 * math.sin(math.radians(94)), 2000 * math.cos(math.radians(94))
    lon = OBSERVER_LON + math.degrees(east_m / (EARTH_MEAN_RADIUS_M * math.cos(math.radians(36.1))))
    lat = OBSERVER_LAT + math.degrees(north_m / EARTH_MEAN_RADIUS_M)
    heights[row_of(lat), col_of(lon)] = GROUND_M + 500

    angles = compute_horizon(point(), tiles(heights)).angles_deg

    assert angles[9] > 5
    assert angles[8] == 0.0


def test_the_observer_stands_at_eye_height_above_the_surface() -> None:
    heights = flat()
    # A ring of cells 1.7 m above the ground is exactly at eye level, so it does not block.
    heights[:, col_of(OBSERVER_LON + 0.01)] = GROUND_M + EYE_HEIGHT_M

    assert compute_horizon(point(), tiles(heights)).angles_deg[9] == 0.0


def test_missing_elevation_along_a_ray_is_an_error_not_an_open_sky() -> None:
    # The grid ends about 5 km east of the observer, so the east rays run off it.
    small = flat()[:, : col_of(OBSERVER_LON + 0.05)]

    with pytest.raises(MissingElevation, match="tp-1"):
        compute_horizon(point(), tiles(small))


def test_max_elevation_angle_takes_the_highest_sample() -> None:
    eye = GROUND_M + EYE_HEIGHT_M
    distances = np.array([500.0, 1000.0, 2000.0])
    heights = np.array([eye + 10, eye + 100, eye + 150])

    drop = 1000.0**2 / (2 * EARTH_MEAN_RADIUS_M)
    expected = math.degrees(math.atan((100 - drop) / 1000))
    assert max_elevation_angle(eye, distances, heights) == pytest.approx(expected)


def test_earth_curvature_lowers_distant_terrain() -> None:
    eye = GROUND_M
    # At 15 km the ground falls about 17.7 m below the level line; terrain that much higher
    # than the eye sits exactly on the horizontal.
    drop = RANGE_M**2 / (2 * EARTH_MEAN_RADIUS_M)
    assert drop == pytest.approx(17.66, abs=0.01)

    angle = max_elevation_angle(eye, np.array([float(RANGE_M)]), np.array([eye + drop]))

    assert angle == pytest.approx(0.0, abs=1e-9)


def test_terrain_below_the_eye_gives_zero_not_a_negative_angle() -> None:
    angle = max_elevation_angle(2000.0, np.array([100.0, 200.0]), np.array([1500.0, 800.0]))

    assert angle == 0.0


def profile(values: list[float]) -> HorizonProfile:
    return HorizonProfile(trail_point_id="tp-1", angles_deg=tuple(values))


def test_horizon_at_a_sector_centre_is_that_sector() -> None:
    horizon = profile([float(i) for i in range(36)])

    assert horizon_at(horizon, 0) == 0.0
    assert horizon_at(horizon, 90) == 9.0
    assert horizon_at(horizon, 350) == 35.0


def test_horizon_at_interpolates_between_sector_centres() -> None:
    horizon = profile([float(i) for i in range(36)])

    assert horizon_at(horizon, 92.5) == pytest.approx(9.25)
    assert horizon_at(horizon, 355) == pytest.approx(17.5)  # halfway from 35 back to 0


def test_horizon_at_accepts_any_azimuth() -> None:
    horizon = profile([float(i) for i in range(36)])

    assert horizon_at(horizon, 450) == 9.0
    assert horizon_at(horizon, -10) == 35.0


def test_validate_horizon_passes_a_good_profile() -> None:
    assert validate_horizon(profile([0.0] * 35 + [89.9])) == []


def test_validate_horizon_lists_every_problem() -> None:
    problems = validate_horizon(profile([0.0] * 33 + [-1.0, 91.0, float("nan")]))

    assert problems == [
        "sector 33: -1.0 is below 0 degrees",
        "sector 34: 91.0 is above 90 degrees",
        "sector 35: nan is not a number",
    ]


def test_validate_horizon_needs_36_angles() -> None:
    assert validate_horizon(profile([0.0] * 35)) == ["expected 36 angles, got 35"]


@pytest.mark.skipif(not REAL_TILE_DIR.exists(), reason=NO_REAL_TILES)
def test_ac_1a_2_canyon_floor_horizon_is_at_least_5_degrees_higher_than_the_rim() -> None:
    real = load_elevation_tiles(sorted(REAL_TILE_DIR.glob("*.tif")))
    rim = [
        point(-112.1435, 36.0574),  # Bright Angel trailhead
        point(-112.0838, 36.0531),  # South Kaibab trailhead
        point(-112.0566, 36.2172),  # North Kaibab trailhead
    ]
    floor = [
        point(-112.0947, 36.1059),  # Phantom Ranch
        point(-112.0949, 36.1012),  # Bright Angel campground
        point(-112.0870, 36.0997),  # Black Bridge over the Colorado River
    ]

    def median_horizon(points: list[TrailPoint]) -> float:
        return float(np.median([np.median(compute_horizon(p, real).angles_deg) for p in points]))

    floor_median, rim_median = median_horizon(floor), median_horizon(rim)

    assert floor_median >= rim_median + 5, (floor_median, rim_median)
