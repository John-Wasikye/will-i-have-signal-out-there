"""Draw the terrain picture and height list the site shows for each main trail.

The site's trail map has a fixed size and fits each trail into it (``trailShape`` in
``app/src/lib/trailSignal.ts``). ``map_grid`` repeats that fit, so every pixel of the picture sits
under the right part of the trail line. Run by hand when a trail changes:

    python pipelines/signal/trail_terrain_art.py <folder of GLO-30 tiles> <API address> app
"""

import json
import struct
import sys
import zlib
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from geotiff import ElevationGrid, read_elevation_grid

MAP_WIDTH = 600
MAP_HEIGHT = 420
MAP_PADDING = 34
IMAGE_WIDTH = 900
IMAGE_HEIGHT = 630
METERS_PER_DEGREE = 111_320.0
CONTOUR_INTERVAL_M = 200
TINT_LEVELS = 32
SHADE_LEVELS = 8
CONTOUR_DARKENING = 3
SMOOTHING_PIXELS = 2
SHADE_RANGE = (0.42, 1.12)
SUN_AZIMUTH_DEG = 315.0
SUN_ALTITUDE_DEG = 45.0
TRAIL_IDS = ("grca-bright-angel", "grca-north-kaibab", "grca-south-kaibab")
# Red river gorge, orange cliffs, pale rock, then the forest on the rims.
TINT_STOPS = ((0.0, (122, 62, 40)), (0.3, (178, 104, 62)), (0.6, (217, 164, 106)),
              (0.8, (226, 205, 158)), (1.0, (146, 160, 108)))  # fmt: skip


def _fit(lons: np.ndarray, lats: np.ndarray, width: int, height: int, padding: int):
    squeeze = np.cos(np.radians((lats.min() + lats.max()) / 2))
    span_x = (lons.max() - lons.min()) * squeeze
    span_y = lats.max() - lats.min()
    scale = min((width - 2 * padding) / (span_x or 1), (height - 2 * padding) / (span_y or 1))
    return squeeze, scale, (width - span_x * scale) / 2, (height - span_y * scale) / 2


def map_grid(
    lons: np.ndarray,
    lats: np.ndarray,
    width: int,
    height: int,
    padding: int,
    out_width: int,
    out_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the longitude and latitude of every pixel of a picture of the map."""
    squeeze, scale, offset_x, offset_y = _fit(lons, lats, width, height, padding)
    x = (np.arange(out_width) + 0.5) / out_width * width
    y = (np.arange(out_height) + 0.5) / out_height * height
    lon = lons.min() + (x - offset_x) / (scale * squeeze)
    lat = lats.min() + (height - offset_y - y) / scale
    return np.meshgrid(lon, lat)


def hillshade(heights: np.ndarray, cell_m: float) -> np.ndarray:
    """Return how brightly a low northwest sun lights each cell, from 0 to 1."""
    down_rows, east = np.gradient(heights, cell_m)
    north = -down_rows
    azimuth = np.radians(SUN_AZIMUTH_DEG)
    altitude = np.radians(SUN_ALTITUDE_DEG)
    sun = (
        np.sin(azimuth) * np.cos(altitude),
        np.cos(azimuth) * np.cos(altitude),
        np.sin(altitude),
    )
    lit = -east * sun[0] - north * sun[1] + sun[2]
    return np.clip(lit / np.sqrt(east**2 + north**2 + 1), 0, 1)


def relief_index(heights: np.ndarray, shade: np.ndarray, low: float, high: float) -> np.ndarray:
    """Return a palette index for each cell: a tint for its height and a level of light."""
    tint = np.clip((heights - low) / (high - low), 0, 1) * (TINT_LEVELS - 1)
    light = np.clip(shade, 0, 1) * (SHADE_LEVELS - 1)
    return (np.rint(tint) * SHADE_LEVELS + np.rint(light)).astype(np.uint8)


def relief_palette() -> np.ndarray:
    """Return the colors that ``relief_index`` points at."""
    stops = np.array([stop for stop, _ in TINT_STOPS])
    colors = np.array([color for _, color in TINT_STOPS], dtype=float)
    position = np.linspace(0, 1, TINT_LEVELS)
    tints = np.stack([np.interp(position, stops, colors[:, c]) for c in range(3)], axis=1)
    lights = np.linspace(*SHADE_RANGE, SHADE_LEVELS)
    palette = tints[:, None, :] * lights[None, :, None]
    return np.clip(palette, 0, 255).reshape(-1, 3).astype(np.uint8)


def contour_mask(heights: np.ndarray, interval: float) -> np.ndarray:
    """Return True on cells where the ground crosses a height line."""
    band = np.floor(heights / interval)
    lines = np.zeros(heights.shape, dtype=bool)
    lines[:, :-1] |= band[:, :-1] != band[:, 1:]
    lines[:-1, :] |= band[:-1, :] != band[1:, :]
    return lines


def _chunk(kind: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(kind + body)
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def indexed_png(pixels: np.ndarray, palette: np.ndarray) -> bytes:
    """Encode palette indexes as a PNG. The image tools here have no other way to write one."""
    height, width = pixels.shape
    header = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    rows = np.hstack([np.zeros((height, 1), dtype=np.uint8), pixels.astype(np.uint8)])
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", header),
            _chunk(b"PLTE", palette.astype(np.uint8).tobytes()),
            _chunk(b"IDAT", zlib.compress(rows.tobytes(), 9)),
            _chunk(b"IEND", b""),
        )
    )


def terrain_module(elevations: dict[str, list[int]]) -> str:
    """Return the TypeScript file that lists each trail's heights, one per trail point."""
    rows = "".join(f"  '{trail}': {heights},\n" for trail, heights in elevations.items())
    return (
        "// Written by pipelines/signal/trail_terrain_art.py. Heights in meters, one per trail "
        "point.\n"
        f"export const TRAIL_ELEVATIONS_M: Record<string, number[]> = {{\n{rows}}}\n"
    )


def _sample(grids: list[ElevationGrid], lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    heights = np.full(np.shape(lon), np.nan)
    for grid in grids:
        found = grid.elevation_at(lon, lat)
        heights = np.where(np.isnan(heights), found, heights)
    return heights


def _smooth(heights: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    padded = np.pad(heights, radius, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, (size, size))
    return windows.mean(axis=(2, 3))


def _terrain_picture(
    grids: list[ElevationGrid], lons: np.ndarray, lats: np.ndarray, low: float, high: float
) -> bytes:
    lon, lat = map_grid(lons, lats, MAP_WIDTH, MAP_HEIGHT, MAP_PADDING, IMAGE_WIDTH, IMAGE_HEIGHT)
    heights = _smooth(_sample(grids, lon, lat), SMOOTHING_PIXELS)
    cell_m = abs(lat[0, 0] - lat[1, 0]) * METERS_PER_DEGREE
    index = relief_index(heights, hillshade(heights, cell_m), low, high)
    light = index % SHADE_LEVELS
    darker = index - np.minimum(light, CONTOUR_DARKENING)
    index = np.where(contour_mask(heights, CONTOUR_INTERVAL_M), darker, index)
    return indexed_png(index, relief_palette())


def main(tiles: Path, api: str, app: Path) -> None:
    """Write each trail's terrain picture and the module of heights."""
    grids = [read_elevation_grid(path) for path in sorted(tiles.glob("*.tif"))]
    elevations: dict[str, list[int]] = {}
    (app / "public" / "trails").mkdir(parents=True, exist_ok=True)
    for trail in TRAIL_IDS:
        with urlopen(f"{api}/trails/{trail}/signal") as answer:
            points = json.load(answer)["points"]
        lons = np.array([point["lon"] for point in points])
        lats = np.array([point["lat"] for point in points])
        elevations[trail] = [int(round(height)) for height in _sample(grids, lons, lats)]
        picture = _terrain_picture(grids, lons, lats, 700.0, 2700.0)
        (app / "public" / "trails" / f"{trail}-terrain.png").write_bytes(picture)
    module = app / "src" / "lib" / "trailElevations.ts"
    module.write_text(terrain_module(elevations), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
