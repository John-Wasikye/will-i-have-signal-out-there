# 0008. Give a coverage confidence only where enough tests exist; use hiker reports as labels

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026); amended Oct 9, 2026 (Decided by John, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Coverage confidence"; build plan 1B.4 and 1B.8; "Decisions and open items"

## Context

The FCC map is a model's claim. Ookla speed tests measure what phones actually got, but speed tests only exist where phones already had signal, so dead zones are missing from the data.

## Decision

- A model predicts how likely the FCC map is to be right, using terrain, distance to the nearest tower and remoteness.
- It gives a confidence level only where enough tests exist nearby. Elsewhere the page says: "Not enough measurements here; the coverage map's claim is unverified."
- Hiker signal reports become labels over time, including the missing no-signal cases, only where enough different visitors agree. Amendment (Decided by John, Oct 9, 2026): "enough agree" means N reports in the same cell on the same day. Because a visitor can report once per cell per 24 hours (ADR 0011), each report in a cell is from a different visitor, so reports need no ID to be counted. N stays an open number. The model retrains once there are enough labels.
- Model inputs (amendment, Decided by John, Oct 9, 2026): terrain, distance to the nearest tower from OpenCelliD, and remoteness defined as distance to the nearest road or trailhead (ADR 0024).

Reason recorded by John: speed tests miss dead zones, so the model must not guess there.

## Alternatives considered

- Giving a confidence level everywhere: rejected, it would guess in dead zones.
- No other alternatives are recorded.

## Consequences

- The page has two states for a point: a confidence level or the notice.
- Open numbers: tests that count as enough and the nearby distance (OQ-14), N reports in a cell per day (OQ-12), labels needed to retrain (OQ-13).
- The model family is logistic regression (ADR 0031). The remoteness data source is still open (OQ-18).
- The day boundary for "same day" is UTC midnight (ADR 0026, OQ-26). The system accepts at most 50 reports a day (ADR 0011), which caps how fast labels can accrue.
