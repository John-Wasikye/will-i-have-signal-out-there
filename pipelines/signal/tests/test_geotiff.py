"""Tests for the GeoTIFF reader that C4 uses for the Copernicus GLO-30 tiles.

The reader handles exactly the layout the first-run check found (OQ-8): tiled, deflate, 32-bit
floats with the floating-point predictor, one band, a pixel scale and one tie point, and
"pixel is point". Each test writes a small TIFF in that layout, so no test needs the real tiles.
The last test reads the real tiles only when they are on this computer.
"""

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from geotiff import ElevationGrid, UnsupportedTiff, read_elevation_grid

# Where the first-run check left the four park tiles on John's laptop. CI does not have them.
REAL_TILE_DIR = Path.home() / "AppData" / "Local" / "Temp" / "p1-checks" / "copernicus"
NO_REAL_TILES = "real Copernicus tiles are only on John's laptop"


def write_tiff(
    path: Path,
    heights: np.ndarray,
    *,
    west: float,
    north: float,
    step_deg: float,
    tile: int = 16,
    predictor: int = 3,
    compression: int = 8,
    raster_type: int = 2,
) -> None:
    """Write ``heights`` (rows from north to south) as a little-endian tiled TIFF."""
    rows, cols = heights.shape
    across, down = -(-cols // tile), -(-rows // tile)
    padded = np.zeros((down * tile, across * tile), dtype=np.float32)
    padded[:rows, :cols] = heights
    blocks = []
    for ty in range(down):
        for tx in range(across):
            block = padded[ty * tile : (ty + 1) * tile, tx * tile : (tx + 1) * tile]
            if predictor == 3:
                planes = block.astype(">f4").view(np.uint8).reshape(tile, tile, 4)
                shuffled = planes.transpose(0, 2, 1).reshape(tile, tile * 4).astype(np.int16)
                shuffled[:, 1:] = shuffled[:, 1:] - shuffled[:, :-1]
                raw = (shuffled % 256).astype(np.uint8).tobytes()
            else:
                raw = block.astype("<f4").tobytes()
            blocks.append(zlib.compress(raw) if compression == 8 else raw)

    geokeys = [1, 1, 0, 1, 1025, 0, 1, raster_type]
    entries = [
        (256, 3, [cols]),
        (257, 3, [rows]),
        (258, 3, [32]),
        (259, 3, [compression]),
        (277, 3, [1]),
        (317, 3, [predictor]),
        (322, 3, [tile]),
        (323, 3, [tile]),
        (324, 4, None),  # tile offsets, filled in below
        (325, 4, [len(b) for b in blocks]),
        (339, 3, [3]),
        (33550, 12, [step_deg, step_deg, 0.0]),
        (33922, 12, [0.0, 0.0, 0.0, west, north, 0.0]),
        (34735, 3, geokeys),
    ]
    fmt = {3: "H", 4: "I", 12: "d"}
    ifd_size = 2 + 12 * len(entries) + 4
    extra_at = 8 + ifd_size
    # Lay out the out-of-line values, then the tile data.
    extra = bytearray()
    out_of_line = {}
    offsets_at = None
    for tag, typ, values in entries:
        count = len(blocks) if values is None else len(values)
        size = struct.calcsize(fmt[typ]) * count
        if size > 4:
            out_of_line[tag] = extra_at + len(extra)
            if values is None:
                offsets_at = len(extra)
            extra += b"\0" * size
    data_at = extra_at + len(extra)
    offsets, at = [], data_at
    for b in blocks:
        offsets.append(at)
        at += len(b)
    entries[8] = (324, 4, offsets)
    if offsets_at is not None:  # one tile's offset fits in the entry itself
        struct.pack_into("<" + "I" * len(offsets), extra, offsets_at, *offsets)
    for tag, typ, values in entries:
        if tag in out_of_line and tag != 324:
            struct.pack_into(
                "<" + fmt[typ] * len(values), extra, out_of_line[tag] - extra_at, *values
            )

    out = bytearray(b"II" + struct.pack("<HI", 42, 8))
    out += struct.pack("<H", len(entries))
    for tag, typ, values in entries:
        if tag in out_of_line:
            value = struct.pack("<I", out_of_line[tag])
        else:
            value = struct.pack("<" + fmt[typ] * len(values), *values).ljust(4, b"\0")
        out += struct.pack("<HHI", tag, typ, len(values)) + value
    out += struct.pack("<I", 0)
    out += extra
    for b in blocks:
        out += b
    path.write_bytes(bytes(out))


def sample_heights(rows: int = 40, cols: int = 37) -> np.ndarray:
    # Every cell different, with a fractional part, so a shifted or swapped byte shows.
    r, c = np.mgrid[0:rows, 0:cols]
    return (1000.0 + r * 10.25 + c * 0.5).astype(np.float32)


def test_reads_every_cell_of_a_tiled_predictor_3_file(tmp_path: Path) -> None:
    heights = sample_heights()
    path = tmp_path / "t.tif"
    write_tiff(path, heights, west=-113.0, north=37.0, step_deg=0.01)

    grid = read_elevation_grid(path)

    np.testing.assert_array_equal(grid.heights, heights)


def test_reads_a_file_without_the_predictor(tmp_path: Path) -> None:
    heights = sample_heights()
    path = tmp_path / "t.tif"
    write_tiff(path, heights, west=-113.0, north=37.0, step_deg=0.01, predictor=1)

    np.testing.assert_array_equal(read_elevation_grid(path).heights, heights)


def test_keeps_the_tie_point_and_cell_size(tmp_path: Path) -> None:
    path = tmp_path / "t.tif"
    write_tiff(path, sample_heights(), west=-113.0, north=37.0, step_deg=0.01)

    grid = read_elevation_grid(path)

    assert (grid.west, grid.north, grid.step_deg) == (-113.0, 37.0, 0.01)


def test_pixel_is_point_means_the_first_cell_is_centred_on_the_tie_point(tmp_path: Path) -> None:
    heights = sample_heights()
    path = tmp_path / "t.tif"
    write_tiff(path, heights, west=-113.0, north=37.0, step_deg=0.01)
    grid = read_elevation_grid(path)

    # Just inside the tie point is cell (0, 0); 0.004 degrees away is still nearer to it.
    lon = np.array([-113.0, -112.996, -112.994, -112.99])
    lat = np.array([37.0, 36.996, 37.0, 36.99])

    np.testing.assert_array_equal(
        grid.elevation_at(lon, lat),
        [heights[0, 0], heights[0, 0], heights[0, 1], heights[1, 1]],
    )


def test_points_outside_the_grid_are_nan(tmp_path: Path) -> None:
    path = tmp_path / "t.tif"
    write_tiff(path, sample_heights(rows=10, cols=10), west=-113.0, north=37.0, step_deg=0.01)
    grid = read_elevation_grid(path)

    values = grid.elevation_at(np.array([-113.5, -112.95, -112.95]), np.array([36.95, 36.0, 36.95]))

    assert np.isnan(values[0]) and np.isnan(values[1])
    assert not np.isnan(values[2])


def test_refuses_pixel_is_area_rather_than_guess(tmp_path: Path) -> None:
    path = tmp_path / "t.tif"
    write_tiff(path, sample_heights(), west=-113.0, north=37.0, step_deg=0.01, raster_type=1)

    with pytest.raises(UnsupportedTiff, match="pixel is point"):
        read_elevation_grid(path)


def test_refuses_an_unexpected_compression(tmp_path: Path) -> None:
    path = tmp_path / "t.tif"
    write_tiff(path, sample_heights(), west=-113.0, north=37.0, step_deg=0.01, compression=1)

    with pytest.raises(UnsupportedTiff, match="compression"):
        read_elevation_grid(path)


def test_grid_can_be_built_in_memory_for_tests() -> None:
    grid = ElevationGrid(np.zeros((3, 3), dtype=np.float32), west=0.0, north=1.0, step_deg=0.5)

    assert grid.elevation_at(np.array([0.5]), np.array([0.5]))[0] == 0.0


@pytest.mark.skipif(not REAL_TILE_DIR.exists(), reason=NO_REAL_TILES)
def test_real_tiles_give_the_published_heights() -> None:
    grid = read_elevation_grid(REAL_TILE_DIR / "N36_00_W113_00.tif")

    assert (grid.west, grid.north, grid.heights.shape) == (-113.0, 37.0, (3600, 3600))
    # Published heights; a 30 m surface model is within a few meters of them on open ground.
    checks = [
        (-112.1435, 36.0574, 2075),  # Bright Angel trailhead, South Rim
        (-112.0947, 36.1059, 783),  # Phantom Ranch, canyon floor
        (-112.0566, 36.2172, 2512),  # North Kaibab trailhead
    ]
    for lon, lat, published in checks:
        height = grid.elevation_at(np.array([lon]), np.array([lat]))[0]
        assert abs(height - published) < 15, (lon, lat, height)
