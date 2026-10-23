# 0035. Remoteness is the distance to the nearest TIGER/Line road or NPS trail line

- Status: Accepted (John, Oct 9, 2026, choosing the first of three options laid out for OQ-18)
- Date: Oct 9, 2026
- Source: Open question OQ-18; ADR 0024 (definition); ADR 0031 (model family)

## Context

The confidence model uses remoteness as an input (ADR 0008). ADR 0024 defined remoteness as the distance to the nearest road or trailhead, but left the data source open. The usual road data (OpenStreetMap) is under the ODbL share-alike licence. Its share-alike duty would reach the confidence values built on it, on top of the Ookla and OpenCelliD duties already there.

## Decision

- **Roads.** U.S. Census Bureau TIGER/Line All Roads county files for the counties that contain the park and a buffer of 15 km around it (contract `tiger_roads`). The Census Bureau declares these files CC0 (public domain) on data.gov.
- **Trailheads.** The NPS Public Trails lines (contract `nps_trails`) stand in for trailheads. The distance is to the nearest point on any trail line, not only to a trailhead point. A separate trailhead dataset is not used, because the trail network is the data already loaded for Phase A.
- **Distance.** For each trail point, the distance in metres to the nearest road segment or trail line, computed after converting both to WGS84. Stored in the internal table `trail_point_remoteness` (proposed).

## Conditions before the first load

- **Licence check (first-run check).** TIGER/Line files carry a rights flag of "otherRestrictions" on some county files. The Census Bureau page for the exact vintage must be read before the first download. If it restricts redistribution, only the computed distances are kept, never the road geometry. The distances are then derived data, and the credit to the Census Bureau stays on the page.
- **Attribution.** Credit the U.S. Census Bureau (TIGER/Line) and the National Park Service on the page and in the README. The NPS's own data-use wording must be checked for the exact dataset used. NPS GIS pages state that the data carry no warranty.

## Alternatives considered

- OpenStreetMap roads. Rejected: share-alike (ODbL) would apply to the confidence values, on top of the existing share-alike terms.
- Dropping remoteness. Not chosen. It remains the fallback if the licence check fails.

## Consequences

- The confidence model gains one input. Its value is tested in the evaluation (OQ-18 and the model card).
- The distance to a trail line is an approximation of the distance to a trailhead. It is recorded as such on the page's methodology notes.
- Two new raw sources (the Census files) need a manifest of URL, size and hash, under standard 1.
