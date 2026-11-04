"""Satellite window engine (C5, design doc 7.B).

For each trail point and each selected Direct-to-Cell satellite, find the minutes when the
satellite is reachable: at or above the minimum elevation and above the terrain horizon in its
direction (ADR 0003). Consecutive reachable minutes are stored as one window with a start and an
end time, never one row per minute (ADR 0005). The run predicts 26 hours from the run's scheduled
time (ADR 0019), and its predictions are valid until the end of that span (ADR 0006).

Positions come from SGP4, the model the CelesTrak elements are made for, in the TEME frame, then
turned into an earth-fixed frame by Greenwich mean sidereal time. Polar motion and the small
difference between UT1 and UTC are left out: together they move a satellite by well under 100 m,
which changes its elevation by far less than the 1-minute step does. The observer stands on the
WGS84 ellipsoid at the trail point's latitude and longitude. Its real height (up to 2.5 km on the
rims) would change a satellite's elevation by about 0.1 degree at 10 degrees, which is also below
the step's accuracy, and the terrain horizon already starts from the ground.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sgp4.api import WGS72, Satrec, SatrecArray, jday
from sgp4.propagation import gstime
from terrain_horizon import SECTOR_WIDTH_DEG, SECTORS, HorizonProfile
from trail_loader import TrailPoint

__all__ = [
    "MIN_ELEVATION_DEG",
    "SENSITIVITY_ELEVATIONS_DEG",
    "SPAN_MINUTES",
    "STEP_MINUTES",
    "MAX_WINDOW_ROWS",
    "PropagationError",
    "RowLimitExceeded",
    "SatelliteElements",
    "SatelliteTrack",
    "Window",
    "compute_valid_until",
    "enforce_row_limit",
    "find_windows",
    "flags_to_windows",
    "look_angles",
    "minute_times",
    "propagate_satellites",
    "reachable_flags",
    "sensitivity_report",
    "teme_positions",
    "teme_to_ecef",
    "windows_for_point",
]

STEP_MINUTES = 1
SPAN_MINUTES = 26 * 60  # 24 hours promised on the page plus the 2-hour nightly maximum (ADR 0019)
MIN_ELEVATION_DEG = 10.0  # ADR 0003
SENSITIVITY_ELEVATIONS_DEG = (5.0, 10.0, 20.0)  # the comparison ADR 0003 asks for (OQ-9)
# John's choice (Nov 4, 2026): about twice the 2,156,029 windows measured from that night's
# 637 satellites and 932 points, so constellation growth fits but a doubling bug stops (ADR 0005).
MAX_WINDOW_ROWS = 4_000_000

SGP4_EPOCH_JD = 2433281.5  # SGP4 counts epochs in days from 1949-12-31 00:00 UTC
WGS84_A_KM = 6378.137
WGS84_E2 = 6.69437999014e-3
MINUTES_PER_DAY = 1440.0


class RowLimitExceeded(RuntimeError):
    """A run would write more windows than its limit, so it stops before anything is written."""


class PropagationError(RuntimeError):
    """SGP4 could not place a satellite, for example because its orbit has decayed."""


@dataclass(frozen=True)
class SatelliteElements:
    """One selected satellite's orbital elements, as the dtc_satellite table holds them."""

    norad_cat_id: int
    object_name: str
    epoch_utc: datetime
    inclination_deg: float
    eccentricity: float
    ra_of_asc_node_deg: float
    arg_of_pericenter_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_per_day: float
    bstar: float

    @classmethod
    def from_row(cls, row: Mapping) -> SatelliteElements:
        """Take the element columns of a dtc_satellite row and ignore the rest."""
        return cls(**{name: row[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class SatelliteTrack:
    """One satellite's earth-fixed positions, in km, one row per minute of the span."""

    satellite_id: str
    ecef_km: np.ndarray


@dataclass(frozen=True)
class Window:
    """One reachable interval for one trail point and satellite: first and last reachable minute."""

    trail_point_id: str
    satellite_id: str
    start_utc: datetime
    end_utc: datetime


def minute_times(start: datetime, minutes: int, step_minutes: int = STEP_MINUTES) -> list[datetime]:
    """Return ``minutes`` times one step apart from ``start``, which must carry a time zone."""
    if start.tzinfo is None:
        raise ValueError(f"{start} has no time zone; give the span start in UTC")
    start = start.astimezone(UTC)
    return [start + timedelta(minutes=i * step_minutes) for i in range(minutes)]


def compute_valid_until(span_start: datetime, span_minutes: int = SPAN_MINUTES) -> datetime:
    """Return the time the run's predictions stop being valid: the end of its span (ADR 0019)."""
    return span_start + timedelta(minutes=span_minutes)


def teme_positions(elements: Sequence[SatelliteElements], times: Sequence[datetime]) -> np.ndarray:
    """Propagate every satellite to every time with SGP4; return TEME positions in km.

    The result has shape (satellites, times, 3). A satellite SGP4 cannot place raises
    ``PropagationError`` naming it, so a bad element set stops the run instead of leaving gaps.
    """
    satellites = SatrecArray([_satrec(e) for e in elements])
    jd, fr = (np.array(part) for part in zip(*(_julian(t) for t in times), strict=True))
    errors, positions, _ = satellites.sgp4(jd, fr)
    failed = sorted({elements[i].norad_cat_id for i in np.flatnonzero(errors.any(axis=1))})
    if failed:
        raise PropagationError(f"SGP4 could not place satellites {failed}")
    return positions


def teme_to_ecef(teme_km: np.ndarray, times: Sequence[datetime]) -> np.ndarray:
    """Turn TEME positions of shape (satellites, times, 3) into earth-fixed ones.

    The frames differ by a turn about the pole through Greenwich mean sidereal time.
    """
    theta = np.array([gstime(sum(_julian(t))) for t in times])
    cos, sin = np.cos(theta), np.sin(theta)
    x, y, z = teme_km[..., 0], teme_km[..., 1], teme_km[..., 2]
    return np.stack([cos * x + sin * y, -sin * x + cos * y, z], axis=-1)


def propagate_satellites(
    elements: Sequence[SatelliteElements], times: Sequence[datetime]
) -> list[SatelliteTrack]:
    """Return each satellite's earth-fixed track over ``times``, propagated once for all points."""
    ecef = teme_to_ecef(teme_positions(elements, times), times)
    return [SatelliteTrack(str(e.norad_cat_id), ecef[i]) for i, e in enumerate(elements)]


def look_angles(
    ecef_km: np.ndarray, lat_deg: float, lon_deg: float, height_m: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Return the azimuth (0 to 360, clockwise from north) and elevation of each position.

    ``ecef_km`` may have any shape ending in 3; the angles have that shape without the 3.
    """
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat, cos_lat, sin_lon, cos_lon = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
    n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * sin_lat**2)
    h = height_m / 1000
    observer = np.array(
        [
            (n + h) * cos_lat * cos_lon,
            (n + h) * cos_lat * sin_lon,
            (n * (1 - WGS84_E2) + h) * sin_lat,
        ]
    )
    d = ecef_km - observer
    east = -sin_lon * d[..., 0] + cos_lon * d[..., 1]
    north = -sin_lat * cos_lon * d[..., 0] - sin_lat * sin_lon * d[..., 1] + cos_lat * d[..., 2]
    up = cos_lat * cos_lon * d[..., 0] + cos_lat * sin_lon * d[..., 1] + sin_lat * d[..., 2]
    azimuth = np.degrees(np.arctan2(east, north)) % 360
    elevation = np.degrees(np.arctan2(up, np.hypot(east, north)))
    return azimuth, elevation


def reachable_flags(
    azimuth_deg: np.ndarray, elevation_deg: np.ndarray, horizon: HorizonProfile, min_elev_deg: float
) -> np.ndarray:
    """Return True where the satellite is at or above ``min_elev_deg`` and above the terrain.

    The terrain angle at each azimuth is interpolated between sector centres, as ``horizon_at``
    does (ADR 0036).
    """
    centres = np.arange(SECTORS) * SECTOR_WIDTH_DEG
    terrain = np.interp(azimuth_deg % 360, centres, horizon.angles_deg, period=360)
    return (elevation_deg >= min_elev_deg) & (elevation_deg > terrain)


def flags_to_windows(
    flags: np.ndarray, times: Sequence[datetime]
) -> list[tuple[datetime, datetime]]:
    """Collapse runs of True into (first minute, last minute) pairs, so no minute row is stored."""
    if len(flags) != len(times):
        raise ValueError(f"{len(flags)} flags for {len(times)} minutes")
    edges = np.diff(np.concatenate(([0], np.asarray(flags, dtype=np.int8), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
    return [(times[s], times[e]) for s, e in zip(starts, ends, strict=True)]


def find_windows(
    point: TrailPoint,
    track: SatelliteTrack,
    horizon: HorizonProfile,
    times: Sequence[datetime],
    min_elev_deg: float = MIN_ELEVATION_DEG,
) -> list[Window]:
    """Return the windows when ``track`` is reachable from ``point``."""
    azimuth, elevation = look_angles(track.ecef_km, point.lat, point.lon)
    flags = reachable_flags(azimuth, elevation, horizon, min_elev_deg)
    return [
        Window(point.trail_point_id, track.satellite_id, start, end)
        for start, end in flags_to_windows(flags, times)
    ]


def windows_for_point(
    point: TrailPoint,
    tracks: Sequence[SatelliteTrack],
    horizon: HorizonProfile,
    times: Sequence[datetime],
    min_elev_deg: float = MIN_ELEVATION_DEG,
) -> list[Window]:
    """Return every satellite's windows from one point, looking at all tracks in one step."""
    if not tracks:
        return []
    azimuth, elevation = look_angles(np.stack([t.ecef_km for t in tracks]), point.lat, point.lon)
    flags = reachable_flags(azimuth, elevation, horizon, min_elev_deg)
    return [
        Window(point.trail_point_id, track.satellite_id, start, end)
        for track, row in zip(tracks, flags, strict=True)
        if row.any()
        for start, end in flags_to_windows(row, times)
    ]


def sensitivity_report(
    points: Iterable[TrailPoint],
    tracks: Sequence[SatelliteTrack],
    horizons: Mapping[str, HorizonProfile],
    times: Sequence[datetime],
    elevations: Sequence[float] = SENSITIVITY_ELEVATIONS_DEG,
) -> dict[float, dict[str, int]]:
    """Count windows and reachable minutes at each minimum elevation, for the design note."""
    report = {elevation: {"windows": 0, "minutes": 0} for elevation in elevations}
    for point in points:
        for elevation in elevations:
            windows = windows_for_point(
                point, tracks, horizons[point.trail_point_id], times, elevation
            )
            report[elevation]["windows"] += len(windows)
            report[elevation]["minutes"] += sum(_minutes(w) for w in windows)
    return report


def enforce_row_limit(df, max_rows: int = MAX_WINDOW_ROWS):  # noqa: ANN001, ANN201
    """Return ``df`` unchanged if its row count is within ``max_rows``; otherwise raise.

    The task fails, so its failure callback records an incident and nothing is published.
    """
    rows = df.count()
    if rows > max_rows:
        raise RowLimitExceeded(f"{rows:,} windows would be written, over the limit of {max_rows:,}")
    return df


def _minutes(window: Window) -> int:
    return int((window.end_utc - window.start_utc) / timedelta(minutes=STEP_MINUTES)) + 1


def _julian(moment: datetime) -> tuple[float, float]:
    t = moment.astimezone(UTC)
    return jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)


def _satrec(e: SatelliteElements) -> Satrec:
    jd, fr = _julian(e.epoch_utc)
    satellite = Satrec()
    satellite.sgp4init(
        WGS72,
        "i",
        e.norad_cat_id,
        (jd - SGP4_EPOCH_JD) + fr,
        e.bstar,
        0.0,  # ndot and nddot: SGP4 does not use them
        0.0,
        e.eccentricity,
        math.radians(e.arg_of_pericenter_deg),
        math.radians(e.inclination_deg),
        math.radians(e.mean_anomaly_deg),
        e.mean_motion_rev_per_day * 2 * math.pi / MINUTES_PER_DAY,  # radians per minute
        math.radians(e.ra_of_asc_node_deg),
    )
    return satellite
