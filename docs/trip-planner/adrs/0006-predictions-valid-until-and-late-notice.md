# 0006. Stamp predictions with a valid until time and show late data with a visible late notice

- Status: Accepted, amended (Decided by John, Oct 9, 2026). The original decision to hide expired satellite windows is superseded.
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Stale predictions" (superseded); Decided by John, Oct 9, 2026 (all five projects show old data with a visible late notice instead of hiding it); build plan 1A.3, 1A.6; engineering standards 3 (idempotent tasks that use the run's data interval) and 15 (timestamps in UTC)

## Context

The session box runs only for the nightly run. If a nightly run fails or is skipped (spot unavailable), the last published satellite windows stop being current while the page is still served. The public page works with the box off. The first version of this decision hid expired satellite windows. John then decided that every project shows old data with a visible late notice and does not hide it.

## Decision

- Each satellite window run is stamped with the time its predictions stop being valid (the end of the prediction span, ADR 0019).
- The page shows "Predictions valid until [time]" in the hiker's local time.
- When the data is late or the run failed, the page still shows the old data, with a visible late notice that includes the time of the last good run. It does not hide it.
- Timestamps are stored in UTC and converted to local time only on the page.
- Rerunning a day replaces only that day: the satellite window table is partitioned by the run's logical date and a rerun overwrites only that partition.

## Alternatives considered

- Hiding expired satellite windows (the original decision): superseded by the late notice rule.
- No other alternatives are recorded.

## Consequences

- The late notice must be unmistakable so old satellite windows are not read as current. The exact definition of "late", the notice wording, and how individual satellite windows already in the past are shown are open (OQ-23).
- The page needs the browser clock to compare with the valid until time.
- The published data must carry the time of the last good run (column `run_started_utc`, field `last_good_run_utc`).
- Supersedes the "expired satellite windows disappear on their own" part of AC-1A.6; see requirements.md.
