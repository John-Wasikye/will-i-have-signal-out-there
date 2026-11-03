# 0038. Terrain horizon: ten rays per sector, and a small GeoTIFF reader instead of rasterio

- Status: Proposed (waiting for John)
- Date: Nov 3, 2026
- Source: Building C4 (build plan 1A.2). ADR 0036 left open how many rays make up one sector's angle; John chose the tile reader on Nov 3, 2026

## Context

ADR 0036 fixed 36 sectors of 10 degrees, but not how one sector's angle is found. One ray down the centre of each sector misses anything between sector centres: a narrow peak 2 km away at 4 degrees off centre lies about 140 m beside the centre ray. The satellite window engine (C5) would then treat that part of the sky as open, which breaks ADR 0036's rule that a window is never predicted where terrain blocks it.

The tiles also have to be read. The standard library for this is rasterio, which bundles GDAL. The newest rasterio needs Python 3.12, and the box and the laptop run Python 3.11, so it would be held at 1.4.4 from December 2025. Its bundled libraries are a frequent source of image-scan findings.

## Decision

| Detail | Value | Why |
|---|---|---|
| Rays per sector | 10, one degree apart, at the sector centre minus 4.5 to plus 4.5 degrees | A sector's angle is the highest of its rays, so a peak anywhere in the sector counts. One degree at 15 km is about 260 m, so a ridge wider than that is never missed |
| Angle below the level line | Stored as 0 degrees | The trail_point_horizon contract allows 0 to 90. C5 never counts a satellite under 10 degrees (ADR 0003), so nothing below 0 is ever needed |
| Height lookup | Nearest grid cell | The ray step equals the 30 m grid (ADR 0036), so each step reads a new cell |
| Tile reader | `pipelines/signal/geotiff.py`: the standard library and numpy | It reads only the layout the first-run check found (OQ-8) and refuses anything else. No GDAL in the image. Tested on written test files and against the published heights at three points on the real tiles |

## Alternatives considered

- One ray per sector centre. Rejected: it can miss blocking terrain, so it is not conservative.
- 100 rays per sector. Rejected: ten times the work for ridges narrower than 26 m at 15 km, below the 30 m grid.
- Bilinear interpolation between cells. Rejected for now: a surface model with trees and buildings has no smooth surface to interpolate, and nearest cell keeps each value a real measurement.
- rasterio. Rejected by John on Nov 3, 2026, for the reasons in the context.

## Consequences

- Each point takes about 0.07 seconds on one laptop core, so the 932 Phase A points need about a minute.
- The AC-1A.2 test on the real tiles passes with a wide margin: the canyon-floor points have a median horizon of about 22 degrees, the rim points about 8.
- Bright Angel trailhead shows a median of about 16 degrees, much higher than South Kaibab trailhead (about 1). The trailhead sits among the trees and buildings of Grand Canyon Village, which the surface model counts as terrain (ADR 0004). That is the expected, conservative effect, not a fault.
- If GLO-30 tiles ever change layout, the reader refuses them with a clear error rather than reading wrong heights.
