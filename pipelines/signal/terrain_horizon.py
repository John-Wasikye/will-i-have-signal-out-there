"""Terrain horizon engine (C4): how high terrain rises around a trail point, out to 15 km.

The heights come from the Copernicus GLO-30 surface model (ADR 0004). The defaults are the
ones ADR 0036 set: 15 km range, a sample every 30 m along each ray, an eye 1.7 m above the
surface model, Earth curvature applied, refraction not applied, and 36 sectors
of 10 degrees with sector 0 centred on north, numbered clockwise.

Each sector's angle is the highest of 10 rays spread one degree apart across the sector, so a
narrow peak between sector centres still blocks the sky (ADR 0038). A horizon below the level
line is stored as 0 degrees, the range the trail_point_horizon contract allows; satellites under
10 degrees are never counted reachable (build plan 1A.3), so nothing below 0 is ever needed.
"""

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from geotiff import ElevationGrid, read_elevation_grid
from trail_loader import EARTH_MEAN_RADIUS_M, TrailPoint

RANGE_M = 15_000
STEP_M = 30
EYE_HEIGHT_M = 1.7
SECTORS = 36
SECTOR_WIDTH_DEG = 360 / SECTORS
RAYS_PER_SECTOR = 10
# Each partition holds all four Phase A tiles (about 200 MB), so four fit easily in the scheduler.
SPARK_PARTITIONS = 4

__all__ = [
    "EARTH_MEAN_RADIUS_M",
    "ElevationTiles",
    "HorizonProfile",
    "MissingElevation",
    "compute_horizon",
    "compute_horizons",
    "horizon_at",
    "load_elevation_tiles",
    "max_elevation_angle",
    "validate_horizon",
]


class MissingElevation(ValueError):
    """A ray left the loaded tiles, so the horizon in that direction is unknown."""


@dataclass(frozen=True)
class HorizonProfile:
    """The 36 horizon angles for one trail point, sector 0 centred on north, clockwise."""

    trail_point_id: str
    angles_deg: tuple[float, ...]


class ElevationTiles:
    """The loaded GLO-30 grids for the park plus the horizon range, looked up together."""

    def __init__(self, grids: Iterable[ElevationGrid]) -> None:
        """Keep the grids in the order given; the first that holds a point answers for it."""
        self.grids = list(grids)

    def elevation_at(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Return the height at each point from whichever grid holds it; NaN where none does."""
        out = np.full(np.shape(lon), np.nan, dtype=np.float64)
        for grid in self.grids:
            missing = np.isnan(out)
            if not missing.any():
                break
            out[missing] = grid.elevation_at(np.asarray(lon)[missing], np.asarray(lat)[missing])
        return out


def load_elevation_tiles(paths: Iterable[Path]) -> ElevationTiles:
    """Read every GLO-30 tile file into one ``ElevationTiles``."""
    return ElevationTiles(read_elevation_grid(path) for path in paths)


def compute_horizon(point: TrailPoint, elevation_tiles: ElevationTiles) -> HorizonProfile:
    """Return the 36 horizon angles around ``point``."""
    ground = elevation_tiles.elevation_at(np.array([point.lon]), np.array([point.lat]))[0]
    if np.isnan(ground):
        raise MissingElevation(f"no elevation under trail point {point.trail_point_id}")
    eye = ground + EYE_HEIGHT_M

    # Ray azimuths: sector s covers centre +- 5 degrees; its rays sit at centre -4.5 to +4.5.
    offsets = (np.arange(RAYS_PER_SECTOR) + 0.5) * (SECTOR_WIDTH_DEG / RAYS_PER_SECTOR)
    offsets -= SECTOR_WIDTH_DEG / 2
    centres = np.arange(SECTORS) * SECTOR_WIDTH_DEG
    azimuths = (centres[:, None] + offsets[None, :]).ravel()
    distances = np.arange(STEP_M, RANGE_M + STEP_M, STEP_M, dtype=np.float64)

    lon, lat = _destinations(point.lon, point.lat, azimuths, distances)
    heights = elevation_tiles.elevation_at(lon, lat)
    if np.isnan(heights).any():
        raise MissingElevation(
            f"rays from trail point {point.trail_point_id} leave the loaded elevation tiles"
        )

    ray_angles = _elevation_angles(eye, distances[None, :], heights).max(axis=1)
    sector_angles = np.maximum(ray_angles.reshape(SECTORS, RAYS_PER_SECTOR).max(axis=1), 0.0)
    return HorizonProfile(
        trail_point_id=point.trail_point_id,
        angles_deg=tuple(float(a) for a in sector_angles),
    )


def compute_horizons(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    points: Sequence[TrailPoint],
    tile_paths: Sequence[Path],
    *,
    partitions: int = SPARK_PARTITIONS,
) -> list[HorizonProfile]:
    """Compute every point's horizon in parallel with Spark, in the points' order.

    Each partition reads the tiles once from ``tile_paths``, which must be readable where Spark
    runs its Python workers (the box's local disk: Spark runs in local mode on the session box).
    """
    paths = [str(path) for path in tile_paths]

    def horizons_for(chunk: Iterable[TrailPoint]) -> Iterator[HorizonProfile]:
        tiles = load_elevation_tiles(Path(path) for path in paths)
        for point in chunk:
            yield compute_horizon(point, tiles)

    return (
        spark.sparkContext.parallelize(list(points), partitions)
        .mapPartitions(horizons_for)
        .collect()
    )


def max_elevation_angle(
    observer_height_m: float, distances_m: np.ndarray, heights_m: np.ndarray
) -> float:
    """Return the highest angle in degrees above the level line along one profile, at least 0.

    ``observer_height_m`` is the eye's height on the same datum as ``heights_m``. Terrain at
    distance d sits d**2 / (2 R) lower than it would on a flat Earth.
    """
    angles = _elevation_angles(observer_height_m, np.asarray(distances_m), np.asarray(heights_m))
    return max(float(angles.max()), 0.0)


def horizon_at(horizon: HorizonProfile, azimuth_deg: float) -> float:
    """Return the horizon angle at any azimuth.

    The value is interpolated linearly between the two nearest sector centres (ADR 0036).
    """
    position = (azimuth_deg % 360) / SECTOR_WIDTH_DEG
    below = math.floor(position)
    fraction = position - below
    a = horizon.angles_deg[below % SECTORS]
    b = horizon.angles_deg[(below + 1) % SECTORS]
    return a + (b - a) * fraction


def validate_horizon(horizon: HorizonProfile) -> list[str]:
    """Return every value-range problem in ``horizon``; an empty list means it passes."""
    if len(horizon.angles_deg) != SECTORS:
        return [f"expected {SECTORS} angles, got {len(horizon.angles_deg)}"]
    problems = []
    for sector, angle in enumerate(horizon.angles_deg):
        if math.isnan(angle):
            problems.append(f"sector {sector}: {angle} is not a number")
        elif angle < 0:
            problems.append(f"sector {sector}: {angle} is below 0 degrees")
        elif angle > 90:
            problems.append(f"sector {sector}: {angle} is above 90 degrees")
    return problems


def _elevation_angles(eye: float, distances: np.ndarray, heights: np.ndarray) -> np.ndarray:
    drop = distances**2 / (2 * EARTH_MEAN_RADIUS_M)
    return np.degrees(np.arctan2(heights - drop - eye, distances))


def _destinations(
    lon: float, lat: float, azimuths_deg: np.ndarray, distances_m: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the (lon, lat) reached along each azimuth at each distance from one point.

    Uses a sphere of the Earth's mean radius. Both arrays have shape (azimuths, distances).
    """
    lat1, lon1 = math.radians(lat), math.radians(lon)
    bearing = np.radians(azimuths_deg)[:, None]
    delta = distances_m[None, :] / EARTH_MEAN_RADIUS_M
    lat2 = np.arcsin(
        math.sin(lat1) * np.cos(delta) + math.cos(lat1) * np.sin(delta) * np.cos(bearing)
    )
    lon2 = lon1 + np.arctan2(
        np.sin(bearing) * np.sin(delta) * math.cos(lat1),
        np.cos(delta) - math.sin(lat1) * np.sin(lat2),
    )
    return np.degrees(lon2), np.degrees(lat2)
