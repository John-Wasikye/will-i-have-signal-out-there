# 0007. Use H3 resolution 9 for FCC files and hiker reports, 8 for Ookla tiles, joined with cell_to_parent

- Status: Accepted (engineering standard 9: pick the H3 resolution from the source; Decisions "Report location")
- Date: Oct 9, 2026
- Source: Build plan engineering standard 9; Build Plan Decisions "Report location"; build plan 1A.4 and 1B.1

## Context

Sources come at different grains: FCC coverage files include H3 resolution 9 hexagons, Ookla tiles are about 600 meters, and trail points are sampled every 50 meters.

## Decision

H3 is a grid of hexagon cells covering the Earth; a higher resolution number means smaller cells. Pick the H3 resolution from the source (the cell just larger than the pixel) and join across sources with cell_to_parent (the H3 function that finds the larger cell containing a smaller one): resolution 9 for FCC files and hiker reports, resolution 8 for 15 arc-second rasters and Ookla tiles, resolution 4 for 0.25 degree weather grids (the last is not used by Project 1). Each trail point is assigned an H3 resolution 9 cell to receive the coverage flag.

Reason recorded by John: trail-spot lists do not scale; H3 works anywhere and matches the FCC grid.

## Alternatives considered

- Lists of trail spots: rejected, they do not scale.
- No other alternatives are recorded.

## Consequences

- Using the source's own cell size avoids false precision and mismatched joins.
- Phase C (every national park, GPX routes) needs no new grid.
- The rule for converting an Ookla tile (about 600 meters) to an H3 resolution 8 cell is a detail the developer settles in the loader. The Ookla file's actual fields are open (OQ-20).
