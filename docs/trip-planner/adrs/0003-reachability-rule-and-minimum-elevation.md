# 0003. A satellite is reachable only above the minimum elevation and the terrain horizon; start at 10 degrees

- Status: Accepted as the starting value (build plan "Decide in 1A.3"); the 5 and 20 degree comparison is pending
- Date: Oct 9, 2026
- Source: Build plan 1A.3 and "Decisions and open items" ("Satellite elevation rule (Project 1)")

## Context

Canyon walls and mountains block the sky. A satellite counts as reachable only if it is high enough in the sky and clear of the terrain in its direction.

## Decision

A satellite counts as reachable from a trail point only when it is above both 10 degrees and the terrain horizon in its direction. 10 degrees is the starting minimum elevation. The design note also records how the satellite windows change at 5 and 20 degrees.

## Alternatives considered

- Minimum elevation of 5 degrees and of 20 degrees: compared in the design note after the first satellite window run (OQ-9). The choice stays at 10 unless that comparison and John's decision change it.

## Consequences

- `find_windows(positions, horizon, min_elev)` takes the minimum elevation as a parameter so the comparison needs no code change.
- The satellite window run records `min_elev` so published rows say which value produced them.
- Windows are accurate to the 1-minute propagation step.
- The prediction span is 26 hours (ADR 0019).
- The horizon comes from a surface model that includes vegetation (ADR 0004), so the horizon is conservative where trees are tall (effect to be measured, OQ-24).
