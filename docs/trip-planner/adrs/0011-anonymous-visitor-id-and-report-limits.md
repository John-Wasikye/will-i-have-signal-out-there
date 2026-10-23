# 0011. Use a random ID created on the phone for report limits; no internet addresses

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026); limits amended Oct 9, 2026 (Decided by John, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Visitor identity" and "Report limits"; build plan 1B.8; "Hiker report limits (Project 1)"

## Context

Reports over time must be limited to stop floods and fake reports, without identifying the hiker.

## Decision

- Visitor identity is a random ID created on the phone only. No internet addresses are used (reason recorded: the most private option).
- Limits (amended, Decided by John, Oct 9, 2026): 10 reports a day per visitor (replaces 10 an hour and 50 a day per visitor), one per cell per visitor every 24 hours, and at most 50 reports a day accepted by the whole system, plus filtering. John raises the caps as traffic grows. Reason recorded earlier: a limit on reports over time stops floods and fake reports.
- Limits are applied by the hour the report was made on the phone (the report's rounded hour), not by arrival time, so a batch sent after being offline is not refused for arriving together (Decided by John, Oct 9, 2026).
- Limit counters are stored apart from the reports and expire, so reports never carry an ID that links them. The build plan sets expiry at 24 hours; the offline delay and the day boundary are decided in ADR 0026 (OQ-26).

## Alternatives considered

- Limits by internet address: not chosen, because John picked the most private option.
- No other alternatives are recorded.

## Consequences

- A visitor can reset their identity by clearing phone storage; filtering and the set-aside step (ADR 0012) cover that.
- Counting for label confirmation uses the one-per-cell rule: N reports in one cell on one day come from N visitors (ADR 0008).
- A phone could state a false report hour. The sub-parts are decided in ADR 0026: UTC day, reports up to 48 hours old, counters kept 72 hours after their day (OQ-26).
- A system-wide counter (no visitor ID) enforces the 50 a day cap.
- Internet addresses are removed from logs (ADR 0023).
- The ID format and transport are decided in ADR 0025 (OQ-38).
