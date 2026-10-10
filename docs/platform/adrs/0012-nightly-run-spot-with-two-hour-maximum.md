# 0012. The nightly run is every night, on spot capacity, stops when done, with a two-hour maximum

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Data freshness" and "Nightly shutdown"). The start time of 10:00 UTC was a Default and is confirmed by John, Oct 9, 2026.
- Date: Oct 9, 2026.

## Context

Data must be fresh every day, and the asteroid brief must be ready each morning (BP, "How the box is run"). Spot capacity is cheaper but can be taken back at short notice.

## Decision

1. The session box starts each night at 10:00 UTC (3 a.m. Arizona, 6 a.m. US Eastern). This is a Default that John may change.
2. It runs every pipeline, publishes, and shuts down when the pipelines finish. It has a hard maximum of 2 hours. A run that reaches the maximum is recorded as an incident, and the next run catches up.
3. Spot only. If spot capacity is unavailable, that night is skipped and the next run catches up safely (BP).
4. Backfills run only in work sessions, never in the nightly run (BP).

## Alternatives considered

- A fixed window: rejected. It could cut a run off partway.
- A weekly run: rejected by John. A daily run costs about $1 a month more and keeps data fresh.

## Consequences

- A skipped night shows old data with a visible late notice (Project 1, ADR 0027). The late threshold is set per project.
- Expected run time is about 45 minutes (BP). Nightly cost is about $2 to $3.35 a month (BP, "Operating model").
- Links: [ADR-0013](0013-cost-guards-and-spend-limits.md); [ADR-0011](0011-always-on-writes-only-to-always-on-storage.md).
