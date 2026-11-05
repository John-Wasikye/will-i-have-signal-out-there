import struct
import zlib

import numpy as np
import trail_terrain_art as art


def test_map_grid_uses_the_same_fit_as_the_site_map():
    lons = np.array([-112.0, -111.9])
    lats = np.array([36.0, 36.1])
    grid_lon, grid_lat = art.map_grid(lons, lats, 600, 400, 20, 600, 400)
    squeeze = np.cos(np.radians(36.05))
    scale = 360 / 0.1
    offset_x = (600 - 0.1 * squeeze * scale) / 2
    # The first trail point sits at this pixel on the site's map (trailShape in trailSignal.ts).
    column, row = round(offset_x), 380
    assert abs(grid_lon[row, column] - (-112.0)) < 0.001
    assert abs(grid_lat[row, column] - 36.0) < 0.001


def test_map_grid_puts_north_at_the_top():
    _, grid_lat = art.map_grid(
        np.array([-112.0, -111.9]), np.array([36.0, 36.1]), 600, 400, 20, 60, 40
    )
    assert grid_lat[0, 0] > grid_lat[-1, 0]


def test_hillshade_lights_slopes_facing_the_northwest_sun():
    faces_west = np.tile(np.arange(50.0), (50, 1)) * 30
    faces_east = faces_west[:, ::-1]
    assert art.hillshade(faces_west, 30.0).mean() > art.hillshade(faces_east, 30.0).mean()


def test_relief_colors_change_with_height():
    heights = np.tile(np.linspace(700, 2700, 64), (64, 1))
    index = art.relief_index(heights, np.full((64, 64), 0.7), 700, 2700)
    assert index[0, 0] != index[0, -1]


def test_contours_mark_only_cells_that_cross_a_line():
    heights = np.tile(np.linspace(1000, 1400, 40), (10, 1))
    lines = art.contour_mask(heights, 200)
    assert 0 < lines.sum() < heights.size / 4


def test_png_is_a_valid_indexed_image():
    pixels = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    palette = np.array([[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)
    data = art.indexed_png(pixels, palette)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, color_type) == (2, 2, 8, 3)
    at = data.index(b"IDAT")
    length = struct.unpack(">I", data[at - 4 : at])[0]
    assert zlib.decompress(data[at + 4 : at + 4 + length]) == b"\x00\x00\x01\x00\x02\x03"


def test_typescript_lists_each_trail_with_its_point_count():
    text = art.terrain_module({"grca-bright-angel": [2100, 2090]})
    assert "'grca-bright-angel': [2100, 2090]" in text
    assert "export const TRAIL_ELEVATIONS_M" in text
