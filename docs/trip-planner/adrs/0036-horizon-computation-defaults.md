# 0036. Terrain horizon computation: defaults for range, ray step, curvature, eye height and the AC-1A.2 margin

- Status: Accepted (John, Oct 9, 2026, approving the defaults proposed for OQ-24)
- Date: Oct 9, 2026
- Source: Open question OQ-24; ADR 0004 (method); AC-1A.2 (requirements, section 6.1)

## Context

ADR 0004 fixed the method and the 36 sectors. OQ-24 listed the details the method still left open: the range, the ray step, curvature and refraction, the observer height, the vegetation question, whether 36 sectors is final, the interpolation, and the numeric margin behind "much higher" in AC-1A.2. Each detail changes which satellite windows are predicted, so each is set here.

## Decision

| Detail | Value | Why |
|---|---|---|
| Range | 15 km from the trail point | Matches the range in ADR 0004 and the build plan |
| Ray step | 30 m along each ray | The spacing of the Copernicus GLO-30 grid, so no grid cell is skipped |
| Observer height | 1.7 m above the surface model | Typical eye height for a standing person |
| Earth curvature | Applied. At 15 km the surface falls about 17 m below the tangent, which lowers the apparent horizon | Leaving it out would overstate how far the ground can be seen |
| Atmospheric refraction | Not applied | Refraction raises distant objects slightly. Leaving it out makes the horizon a little higher, so the prediction is conservative: it predicts fewer windows, never more |
| Surface model | Kept as is, with vegetation and buildings counted as terrain | Conservative for the same reason. The effect is recorded as a limitation (ADR 0004) |
| Sectors | 36 sectors of 10 degrees, sector 0 centred on north, numbered clockwise. This is final | Matches the Documentation Plan's example |
| Between sectors | `horizon_at` interpolates linearly between the two nearest sector centres | Avoids a jump when a satellite's azimuth crosses a sector edge |
| AC-1A.2 margin | The median horizon of the canyon-floor points is at least 5 degrees higher than the median horizon of the rim points in the test fixture | Gives "much higher" a number. The test fixture is the one AC-1A.2 already names |

## Alternatives considered

- Refraction applied. Rejected: its value depends on air conditions, which the pipeline does not model, and the prediction would be less conservative.
- Ray step of 10 m or 90 m. Rejected: 10 m oversamples the 30 m data, and 90 m skips grid cells.
- Nearest sector instead of interpolation. Rejected: it creates jumps in the satellite window edges.

## Consequences

- The horizon is conservative: a satellite window can be missed where the surface model overstates a tree or a building, but a window is never predicted that the terrain blocks.
- The 5-degree margin is a test threshold. If the measured canyon and rim fixture shows a smaller difference, the threshold is revisited with a new ADR, not silently changed.
- Changing any value here changes the satellite windows, so each change needs a new ADR and a rerun of the affected days.
