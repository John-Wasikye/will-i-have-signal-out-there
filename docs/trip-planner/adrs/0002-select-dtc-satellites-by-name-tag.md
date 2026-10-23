# 0002. Select Direct-to-Cell satellites by the [DTC] name tag, cross-checked by altitude and inclination

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Satellite selection"; build plan 1A.1 and "Decisions and open items"

## Context

The page needs to know which Starlink satellites can send Direct-to-Cell texts. CelesTrak (a public source of satellite orbit data) lists the Starlink satellites, and its list carries a [DTC] tag in satellite names. John confirmed the tag exists.

## Decision

Select satellites by the [DTC] tag in their names. Cross-check each selected satellite against altitude (about 330 to 370 km) and inclination (43 or 53 degrees). Any disagreement is logged and listed. The selection is unit-tested.

## Alternatives considered

- Altitude and inclination alone: kept only as the cross-check, not as the selector.
- No other alternatives are recorded.

## Consequences

- If CelesTrak renames or drops the tag, the cross-check log shows disagreements, so the selection does not change silently.
- The weekly source smoke test (ADR 0018, Phase B) and the contract diff catch format changes.
- Whether the tag-based selection agrees with the cross-check on a real file is a first-run check (OQ-6).
- "About 330 to 370 km" has no tighter tolerance in the sources. The developer sets the exact comparison rule when implementing the check and records it in the unit test.
