"""Read Copernicus GLO-30 elevation tiles (GeoTIFF) with the standard library and numpy (C4).

The reader handles exactly the layout the first-run check found (OQ-8): one band of 32-bit
floats, tiled, deflate-compressed, with or without the floating-point predictor, placed by one
tie point and a pixel scale in plain longitude and latitude, and "pixel is point" (the first
cell is centred on the tie point). Anything else is refused with ``UnsupportedTiff`` rather than
read wrongly. Only the first image of the file is read; the overviews after it are not needed.
"""

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# TIFF tags used here (TIFF 6.0 and the GeoTIFF 1.1 specification).
IMAGE_WIDTH, IMAGE_LENGTH, BITS_PER_SAMPLE, COMPRESSION = 256, 257, 258, 259
SAMPLES_PER_PIXEL, PREDICTOR, SAMPLE_FORMAT = 277, 317, 339
TILE_WIDTH, TILE_LENGTH, TILE_OFFSETS, TILE_BYTE_COUNTS = 322, 323, 324, 325
MODEL_PIXEL_SCALE, MODEL_TIEPOINT, GEO_KEY_DIRECTORY = 33550, 33922, 34735
GT_RASTER_TYPE_KEY, RASTER_PIXEL_IS_POINT = 1025, 2
DEFLATE, ADOBE_DEFLATE = 8, 32946
NO_PREDICTOR, FLOATING_POINT_PREDICTOR = 1, 3
IEEE_FLOAT = 3

FIELD_FORMATS = {3: "H", 4: "I", 12: "d", 16: "Q"}


class UnsupportedTiff(ValueError):
    """The file is not in the one layout this reader handles."""


@dataclass(frozen=True)
class ElevationGrid:
    """Heights in meters, rows from north to south, with cell (0, 0) centred on (west, north)."""

    heights: np.ndarray
    west: float
    north: float
    step_deg: float

    def elevation_at(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """Return the nearest cell's height for each point; NaN where a point is off the grid."""
        cols = np.rint((np.asarray(lon) - self.west) / self.step_deg).astype(np.int64)
        rows = np.rint((self.north - np.asarray(lat)) / self.step_deg).astype(np.int64)
        n_rows, n_cols = self.heights.shape
        inside = (rows >= 0) & (rows < n_rows) & (cols >= 0) & (cols < n_cols)
        out = np.full(cols.shape, np.nan, dtype=np.float64)
        out[inside] = self.heights[rows[inside], cols[inside]]
        return out


def read_elevation_grid(path: Path) -> ElevationGrid:
    """Read the first image of a GLO-30 GeoTIFF into an ``ElevationGrid``."""
    data = Path(path).read_bytes()
    order, tags = _first_ifd(data)

    _require(tags.get(BITS_PER_SAMPLE) == (32,), "32-bit samples")
    _require(tags.get(SAMPLE_FORMAT) == (IEEE_FLOAT,), "floating-point samples")
    _require(tags.get(SAMPLES_PER_PIXEL, (1,)) == (1,), "one band")
    compression = tags.get(COMPRESSION, (1,))[0]
    _require(compression in (DEFLATE, ADOBE_DEFLATE), f"deflate compression, not {compression}")
    predictor = tags.get(PREDICTOR, (NO_PREDICTOR,))[0]
    _require(predictor in (NO_PREDICTOR, FLOATING_POINT_PREDICTOR), f"predictor {predictor}")
    _require(TILE_WIDTH in tags and TILE_OFFSETS in tags, "a tiled layout")
    _require(_raster_type(tags) == RASTER_PIXEL_IS_POINT, "pixel is point")
    scale, tiepoint = tags.get(MODEL_PIXEL_SCALE), tags.get(MODEL_TIEPOINT)
    _require(scale is not None and tiepoint is not None, "a pixel scale and a tie point")
    _require(scale[0] == scale[1], "square cells")
    _require(tiepoint[:2] == (0.0, 0.0), "a tie point on cell (0, 0)")

    width, length = tags[IMAGE_WIDTH][0], tags[IMAGE_LENGTH][0]
    tile_w, tile_h = tags[TILE_WIDTH][0], tags[TILE_LENGTH][0]
    across, down = -(-width // tile_w), -(-length // tile_h)
    offsets, counts = tags[TILE_OFFSETS], tags[TILE_BYTE_COUNTS]
    _require(len(offsets) == across * down, "one offset per tile")

    heights = np.empty((down * tile_h, across * tile_w), dtype=np.float32)
    for k, (offset, count) in enumerate(zip(offsets, counts, strict=True)):
        raw = zlib.decompress(data[offset : offset + count])
        block = _decode_block(raw, tile_w, tile_h, order, predictor)
        ty, tx = divmod(k, across)
        heights[ty * tile_h : (ty + 1) * tile_h, tx * tile_w : (tx + 1) * tile_w] = block

    return ElevationGrid(
        heights=heights[:length, :width],
        west=tiepoint[3],
        north=tiepoint[4],
        step_deg=scale[0],
    )


def _decode_block(raw: bytes, width: int, height: int, order: str, predictor: int) -> np.ndarray:
    if predictor == NO_PREDICTOR:
        return np.frombuffer(raw, dtype=order + "f4").reshape(height, width)
    # Floating-point predictor (Adobe Technical Note 3): each row holds the most significant
    # byte of every sample, then the next byte of every sample, and so on, stored as differences
    # from the byte before. Summing each row with 8-bit wrap-around undoes the differences.
    shuffled = np.frombuffer(raw, dtype=np.uint8).reshape(height, width * 4)
    summed = np.cumsum(shuffled, axis=1, dtype=np.uint8)
    big_endian = summed.reshape(height, 4, width).transpose(0, 2, 1).copy()
    return big_endian.view(">f4").reshape(height, width)


def _first_ifd(data: bytes) -> tuple[str, dict[int, tuple]]:
    byte_order = {b"II": "<", b"MM": ">"}.get(data[:2])
    if byte_order is None or struct.unpack_from(byte_order + "H", data, 2)[0] != 42:
        raise UnsupportedTiff("not a classic TIFF file")
    at = struct.unpack_from(byte_order + "I", data, 4)[0]
    (n_entries,) = struct.unpack_from(byte_order + "H", data, at)
    tags = {}
    for i in range(n_entries):
        tag, field_type, count = struct.unpack_from(byte_order + "HHI", data, at + 2 + 12 * i)
        fmt = FIELD_FORMATS.get(field_type)
        if fmt is None:
            continue  # text and other types this reader does not use
        size = struct.calcsize(fmt) * count
        value_at = at + 2 + 12 * i + 8
        if size > 4:
            value_at = struct.unpack_from(byte_order + "I", data, value_at)[0]
        tags[tag] = struct.unpack_from(byte_order + fmt * count, data, value_at)
    return byte_order, tags


def _raster_type(tags: dict[int, tuple]) -> int | None:
    keys = tags.get(GEO_KEY_DIRECTORY, ())
    # Header of 4 values, then one (key, location, count, value) entry per key.
    for i in range(4, len(keys) - 3, 4):
        key, location, _count, value = keys[i : i + 4]
        if key == GT_RASTER_TYPE_KEY and location == 0:
            return value
    return None


def _require(condition: bool, what: str) -> None:
    if not condition:
        raise UnsupportedTiff(f"expected {what}")
