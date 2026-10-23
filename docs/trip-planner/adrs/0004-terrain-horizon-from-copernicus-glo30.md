# 0004. Compute the terrain horizon from Copernicus GLO-30 at trail points sampled every 50 meters

- Status: Accepted (build plan 1A.2; trail and terrain data "Answered")
- Date: Oct 9, 2026
- Source: Build plan 1A.2 and "Decisions and open items"; Documentation Plan "Answered by research"

## Context

The satellite windows depend on how much sky the terrain blocks at each trail point. The build plan fixes the inputs and the procedure; the data formats were answered by research.

## Decision

- Trail lines come from the National Park Service (NPS) Public Trails ArcGIS service for Grand Canyon, limited in Phase A to Bright Angel, South Kaibab and North Kaibab (ADR 0020) (polylines, GeoJSON output, 2,000 records per request, trail name in `TRLNAME`, park in `UNITCODE`).
- A point is sampled every 50 meters.
- Elevation comes from the Copernicus 30-meter model on AWS (GLO-30: heights on the EGM2008 datum, a surface model that includes vegetation and buildings, water flattened; free under the Copernicus licence, with credit).
- Each point's horizon is how high the terrain rises in each compass direction out to about 15 km. Spark (the batch data-processing engine) computes it for many points at the same time and stores it in Iceberg (a table format on S3).
- The horizon is stored as 36 horizon angles per point (the figure used in the Documentation Plan's example for `compute_horizon`).

## Alternatives considered

- No other elevation source or sampling spacing is recorded.

## Consequences

- Because GLO-30 is a surface model (it measures the top of trees and buildings, not bare ground), trees and buildings count as terrain, so horizons may be higher than rock alone.
- Public archives that never change store a manifest of URL, size and hash instead of a full copy (engineering standard 1: keep raw files unchanged, or a manifest for public archives that never change).
- The exact range cutoff, ray step, Earth curvature and refraction handling, observer height, sector convention and the numeric margin for "much higher" are open (OQ-24).
- 36 sectors is taken from the Documentation Plan's example; it is final only after John's review (OQ-24).
- The number of trail points is unknown until the NPS file is loaded; it drives the satellite window row count (OQ-1).
