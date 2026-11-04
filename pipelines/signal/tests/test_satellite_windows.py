"""Tests for the satellite window engine (C5): when a Direct-to-Cell satellite is above both the
minimum elevation and the terrain horizon at a trail point (ADR 0003), stored as start and end
times, never one row per minute (ADR 0005), for a 26-hour span (ADR 0019).

Propagation is checked against Vallado's published SGP4 test case for satellite 00005, so the
unit conversions from the CelesTrak columns are tested against a known answer. The geometry
tests place made-up satellites at chosen directions from an observer.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from satellite_windows import (
    MAX_WINDOW_ROWS,
    MIN_ELEVATION_DEG,
    SPAN_MINUTES,
    PropagationError,
    RowLimitExceeded,
    SatelliteElements,
    SatelliteTrack,
    Window,
    compute_valid_until,
    enforce_row_limit,
    find_windows,
    flags_to_windows,
    look_angles,
    minute_times,
    propagate_satellites,
    reachable_flags,
    sensitivity_report,
    teme_positions,
    teme_to_ecef,
    windows_for_point,
)
from terrain_horizon import SECTORS, HorizonProfile, horizon_at
from trail_loader import TrailPoint

WGS84_A_KM = 6378.137
START = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)

# Vallado, Crawford, Hujsak and Kelso, "Revisiting Spacetrack Report #3" (2006), test case 00005:
# 1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753
# 2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667
SAT_00005 = SatelliteElements(
    norad_cat_id=5,
    object_name="VANGUARD 1",
    epoch_utc=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=178.78495062),
    inclination_deg=34.2682,
    eccentricity=0.1859667,
    ra_of_asc_node_deg=348.7242,
    arg_of_pericenter_deg=331.7664,
    mean_anomaly_deg=19.3264,
    mean_motion_rev_per_day=10.82419157,
    bstar=0.28098e-4,
)
# Position at the epoch in the TEME frame, km, from the same paper's verification output.
SAT_00005_AT_EPOCH_KM = (7022.46529266, -1400.08296755, 0.03995155)


def point(lat: float = 0.0, lon: float = 0.0) -> TrailPoint:
    return TrailPoint("grca-test-00000", "grca-test", "Test", "GRCA", 0, lon, lat)


def flat_horizon(angle: float = 0.0) -> HorizonProfile:
    return HorizonProfile("grca-test-00000", (angle,) * SECTORS)


def at_direction(azimuth_deg: float, elevation_deg: float, range_km: float = 1_000.0) -> np.ndarray:
    """ECEF position of a satellite seen from (lat 0, lon 0, height 0) at the given direction.

    There, up is +x, east is +y and north is +z.
    """
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    up, east, north = np.sin(el), np.cos(el) * np.sin(az), np.cos(el) * np.cos(az)
    return np.array([WGS84_A_KM, 0.0, 0.0]) + range_km * np.array([up, east, north])


def track_through(elevations: list[float], azimuth_deg: float = 0.0) -> SatelliteTrack:
    return SatelliteTrack("99999", np.array([at_direction(azimuth_deg, e) for e in elevations]))


# --- times and validity -------------------------------------------------------------------------


def test_minute_times_are_one_minute_apart_from_the_start():
    assert minute_times(START, 3) == [
        START,
        START + timedelta(minutes=1),
        START + timedelta(minutes=2),
    ]


def test_minute_times_refuse_a_time_without_a_zone():
    with pytest.raises(ValueError, match="UTC"):
        minute_times(datetime(2026, 11, 4, 10, 0), 3)


def test_the_span_is_26_hours_of_minutes():
    assert SPAN_MINUTES == 26 * 60


def test_predictions_are_valid_until_the_end_of_the_span():
    assert compute_valid_until(START) == datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


# --- propagation --------------------------------------------------------------------------------


def test_propagation_matches_the_published_sgp4_test_case():
    positions = teme_positions([SAT_00005], [SAT_00005.epoch_utc])
    assert positions.shape == (1, 1, 3)
    np.testing.assert_allclose(positions[0, 0], SAT_00005_AT_EPOCH_KM, atol=1e-3)


def test_teme_to_ecef_turns_by_sidereal_time():
    # At J2000.0 (2000-01-01 12:00 UT) Greenwich mean sidereal time is 280.46061837 degrees, so a
    # vector on the TEME x axis points to longitude -280.46061837, which is 79.53938163 east.
    j2000 = datetime(2000, 1, 1, 12, 0, tzinfo=UTC)
    ecef = teme_to_ecef(np.array([[[7000.0, 0.0, 0.0]]]), [j2000])[0, 0]
    assert np.degrees(np.arctan2(ecef[1], ecef[0])) == pytest.approx(79.53938163, abs=1e-4)
    assert np.linalg.norm(ecef) == pytest.approx(7000.0)
    assert ecef[2] == pytest.approx(0.0)


def test_a_dtc_shell_satellite_stays_in_its_shell():
    elements = SatelliteElements(
        norad_cat_id=60000,
        object_name="STARLINK-99999 [DTC]",
        epoch_utc=START - timedelta(hours=6),
        inclination_deg=53.0,
        eccentricity=0.0001,
        ra_of_asc_node_deg=120.0,
        arg_of_pericenter_deg=90.0,
        mean_anomaly_deg=10.0,
        mean_motion_rev_per_day=15.85,
        bstar=0.0001,
    )
    times = minute_times(START, 120)
    (track,) = propagate_satellites([elements], times)
    assert track.satellite_id == "60000"
    assert track.ecef_km.shape == (120, 3)
    radius = np.linalg.norm(track.ecef_km, axis=1)
    assert np.all((radius > WGS84_A_KM + 250) & (radius < WGS84_A_KM + 450))
    latitude = np.degrees(np.arcsin(track.ecef_km[:, 2] / radius))
    assert np.abs(latitude).max() < 53.5


def test_elements_are_read_from_a_dtc_satellite_row():
    row = {name: getattr(SAT_00005, name) for name in SatelliteElements.__dataclass_fields__}
    row |= {"perigee_km": 650.0, "apogee_km": 3_800.0, "content_sha256": "abc"}
    assert SatelliteElements.from_row(row) == SAT_00005


# --- look angles --------------------------------------------------------------------------------


def test_a_satellite_straight_up_is_at_90_degrees():
    _, elevation = look_angles(np.array([[WGS84_A_KM + 400, 0.0, 0.0]]), 0.0, 0.0)
    assert elevation[0] == pytest.approx(90.0)


def test_straight_up_follows_the_ellipsoid_normal_away_from_the_equator():
    lat, lon = np.radians(36.05), np.radians(-112.14)
    # Point on the WGS84 ellipsoid, then 500 km out along its normal.
    e2 = 6.69437999014e-3
    n = WGS84_A_KM / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    surface = np.array(
        [n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)]
    )
    normal = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    _, elevation = look_angles(np.array([surface + 500 * normal]), 36.05, -112.14)
    assert elevation[0] == pytest.approx(90.0, abs=1e-6)


@pytest.mark.parametrize("azimuth", [0.0, 90.0, 180.0, 270.0, 33.0])
def test_azimuth_and_elevation_come_back_as_placed(azimuth):
    az, el = look_angles(np.array([at_direction(azimuth, 25.0)]), 0.0, 0.0)
    assert az[0] == pytest.approx(azimuth, abs=1e-9)
    assert el[0] == pytest.approx(25.0, abs=1e-9)


def test_azimuth_is_between_0_and_360():
    az, _ = look_angles(np.array([at_direction(350.0, 25.0)]), 0.0, 0.0)
    assert az[0] == pytest.approx(350.0)


# --- reachability -------------------------------------------------------------------------------


def test_reachable_needs_the_minimum_elevation():
    flags = reachable_flags(
        np.array([0.0, 0.0, 0.0]), np.array([9.9, 10.0, 45.0]), flat_horizon(), 10.0
    )
    assert flags.tolist() == [False, True, True]


def test_reachable_needs_the_satellite_above_the_terrain():
    flags = reachable_flags(
        np.array([0.0, 0.0, 0.0]), np.array([15.0, 20.0, 25.0]), flat_horizon(20.0), 10.0
    )
    assert flags.tolist() == [False, False, True]


def test_reachable_reads_the_terrain_in_the_satellite_direction():
    angles = [0.0] * SECTORS
    angles[9] = 30.0  # sector 9 is centred on east (90 degrees)
    horizon = HorizonProfile("grca-test-00000", tuple(angles))
    flags = reachable_flags(
        np.array([90.0, 270.0, 95.0]), np.array([20.0, 20.0, 20.0]), horizon, 10.0
    )
    # At 95 degrees the horizon is halfway between 30 (at 90) and 0 (at 100): 15, so 20 clears it.
    assert flags.tolist() == [False, True, True]


# --- windows ------------------------------------------------------------------------------------


def test_consecutive_reachable_minutes_become_one_window():
    times = minute_times(START, 6)
    flags = np.array([False, True, True, False, True, True])
    assert flags_to_windows(flags, times) == [(times[1], times[2]), (times[4], times[5])]


def test_no_reachable_minute_means_no_window():
    assert flags_to_windows(np.zeros(4, dtype=bool), minute_times(START, 4)) == []


def test_a_single_minute_window_starts_and_ends_on_that_minute():
    times = minute_times(START, 3)
    assert flags_to_windows(np.array([True, False, False]), times) == [(times[0], times[0])]


def test_flags_and_times_must_line_up():
    with pytest.raises(ValueError, match="minutes"):
        flags_to_windows(np.array([True, False]), minute_times(START, 3))


def test_find_windows_for_a_pass_over_the_point():
    times = minute_times(START, 7)
    track = track_through([-5.0, 5.0, 12.0, 30.0, 12.0, 5.0, -5.0])
    assert find_windows(point(), track, flat_horizon(), times) == [
        Window("grca-test-00000", "99999", times[2], times[4]),
    ]


def test_find_windows_cuts_a_pass_behind_the_canyon_wall():
    times = minute_times(START, 7)
    track = track_through([-5.0, 5.0, 12.0, 30.0, 12.0, 5.0, -5.0])
    assert find_windows(point(), track, flat_horizon(20.0), times) == [
        Window("grca-test-00000", "99999", times[3], times[3]),
    ]


def test_find_windows_uses_10_degrees_by_default():
    assert MIN_ELEVATION_DEG == 10.0


def test_sensitivity_counts_windows_and_minutes_at_5_10_and_20_degrees():
    times = minute_times(START, 7)
    track = track_through([-5.0, 6.0, 12.0, 30.0, 12.0, 6.0, -5.0])
    report = sensitivity_report([point()], [track], {"grca-test-00000": flat_horizon()}, times)
    assert report == {
        5.0: {"windows": 1, "minutes": 5},
        10.0: {"windows": 1, "minutes": 3},
        20.0: {"windows": 1, "minutes": 1},
    }


def test_all_satellites_at_once_gives_the_same_windows_as_one_at_a_time():
    times = minute_times(START, 7)
    tracks = [
        SatelliteTrack("1", track_through([-5.0, 12.0, 30.0, 12.0, -5.0, -5.0, -5.0]).ecef_km),
        SatelliteTrack(
            "2", track_through([-5.0, -5.0, -5.0, 15.0, 40.0, 15.0, -5.0], 200.0).ecef_km
        ),
        SatelliteTrack("3", track_through([-5.0] * 7).ecef_km),
    ]
    one_at_a_time = [w for t in tracks for w in find_windows(point(), t, flat_horizon(), times)]
    assert windows_for_point(point(), tracks, flat_horizon(), times) == one_at_a_time
    assert len(one_at_a_time) == 2


@pytest.mark.parametrize("azimuth", [0.0, 4.0, 95.0, 181.5, 355.0, 359.9])
def test_the_terrain_angle_matches_horizon_at(azimuth):
    horizon = HorizonProfile("grca-test-00000", tuple(float(i % 7) * 3 for i in range(SECTORS)))
    terrain = horizon_at(horizon, azimuth)
    flags = reachable_flags(
        np.array([azimuth, azimuth]), np.array([terrain - 1e-6, terrain + 1e-6]), horizon, 0.0
    )
    assert flags.tolist() == [False, True]


def test_a_satellite_sgp4_cannot_place_stops_the_run():
    decayed = SatelliteElements(
        norad_cat_id=12345,
        object_name="DECAYED",
        epoch_utc=START,
        inclination_deg=53.0,
        eccentricity=0.5,  # perigee far below the ground
        ra_of_asc_node_deg=0.0,
        arg_of_pericenter_deg=0.0,
        mean_anomaly_deg=0.0,
        mean_motion_rev_per_day=15.9,
        bstar=0.0001,
    )
    with pytest.raises(PropagationError, match="12345"):
        teme_positions([SAT_00005, decayed], minute_times(START, 60))


class _Counted:
    """Stands in for a Spark DataFrame: only count() is used."""

    def __init__(self, rows: int) -> None:
        self.rows = rows

    def count(self) -> int:
        return self.rows


def test_the_row_limit_is_4_million():
    # John's choice (Nov 4, 2026): about twice the 2,156,029 rows measured that night.
    assert MAX_WINDOW_ROWS == 4_000_000


def test_a_run_at_the_limit_goes_through():
    frame = _Counted(4_000_000)
    assert enforce_row_limit(frame) is frame


def test_a_run_over_the_limit_stops_before_it_is_written():
    with pytest.raises(RowLimitExceeded, match="4,000,001 .* 4,000,000"):
        enforce_row_limit(_Counted(4_000_001))
