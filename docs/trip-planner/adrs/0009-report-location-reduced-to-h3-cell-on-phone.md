# 0009. Reduce a report's location to an H3 cell on the phone; exact coordinates never leave it

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026); phase confirmed as B (Decided by John, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Report location" (the label "(A)" there is a typo; Decided by John, Oct 9, 2026: the feature is step 1B.8, Phase B); build plan 1B.8; "Personal data"

## Context

Hikers report where they did or did not have signal. Exact positions are personal data and add nothing the coverage grain needs.

## Decision

When a hiker taps a report button, the phone reads its GPS, converts it to an H3 resolution 9 cell (the FCC coverage grain, about 0.1 km2, about 350 m across) with the h3-js library and discards the exact coordinates on the phone. The report holds only the cell, carrier, signal yes or no and the time rounded to the hour.

Reason recorded by John: trail-spot lists do not scale; H3 works anywhere and matches the FCC grid.

## Alternatives considered

- Sending exact coordinates: not chosen; it conflicts with the personal-data decision.
- Trail-spot lists: rejected, they do not scale.

## Consequences

- The server cannot recover exact positions; verified by a request-capture test (AC-1B.8).
- Reports and FCC cells join directly at resolution 9.
- The cell is still a location; the 30-day expiry (ADR 0012) and the absence of an ID (ADR 0011) limit what it reveals.
