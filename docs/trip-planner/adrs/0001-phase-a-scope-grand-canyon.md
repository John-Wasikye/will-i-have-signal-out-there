# 0001. Phase A scope is Grand Canyon main trails, one carrier, the next 24 hours

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions, Project 1 table, "Phase A scope"

## Context

Phase A (the first build stage, "live") is the smallest version that works end to end, on a small area or sample, using the same technology as the full version, and it goes public as soon as it works. Project 1 needs terrain that blocks the sky strongly enough that the satellite-blocking effect is obvious.

## Decision

Phase A covers Grand Canyon National Park's main trails (Bright Angel, South Kaibab and North Kaibab, ADR 0020), one carrier (T-Mobile, ADR 0020), and the next 24 hours of satellite passes (26 hours are predicted so there is no daily gap, ADR 0019). Reason recorded by John: canyon walls make the satellite-blocking effect obvious.

## Alternatives considered

- Wider scope (every carrier, other parks, longer prediction span): recorded as later phases. Every carrier and measured speeds are Phase B (1B.1); every national park is Phase C.
- No other alternatives are recorded.

## Consequences

- One carrier means a single coverage flag per trail point in Phase A.
- The span limits what the page and the Phase B assistant can say about later days (ADR 0021).
- Carrier and trails are decided in ADR 0020; FCC technologies are decided in ADR 0031 (OQ-11).
