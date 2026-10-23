# 0005. Store satellite windows as start and end times, never one row per minute

- Status: Accepted (build plan "Hard limits on everything that costs money")
- Date: Oct 9, 2026
- Source: Build plan "Hard limits" table, "Satellite windows (Project 1)"; Decisions "Surprise costs"

## Context

Propagation runs at 1-minute steps for the 26-hour prediction span (ADR 0019). Storing one row per trail point, satellite and minute would multiply the row count, and nothing in the project is allowed to surprise with cost.

## Decision

Windows are stored as start and end times. A size estimate goes in the design note before step 1A.3 and the row limit is set from it. A job that would exceed its row limit or runtime limit stops before publishing and opens an incident (a recorded failure with its cause and fix).

## Alternatives considered

- One row per minute: rejected by the build plan as the cost and size risk.

## Consequences

- `flags_to_windows` collapses consecutive reachable minutes into intervals.
- The row limit value cannot be set before the test run on the session box (OQ-1, OQ-15).
- The satellite window table partition is the run's logical date so rerunning a day replaces only that day (ADR 0006).
