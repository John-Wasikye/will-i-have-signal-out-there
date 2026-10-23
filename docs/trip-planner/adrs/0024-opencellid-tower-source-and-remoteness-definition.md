# 0024. Use OpenCelliD tower locations and define remoteness as distance to the nearest road or trailhead

- Status: Accepted (Decided by John, Oct 9, 2026); the remoteness data source is still to be chosen
- Date: Oct 9, 2026
- Source: Decided by John, Oct 9, 2026, to give the confidence model a tower-distance input and a definition of remoteness
- Amends: ADR 0008

## Context

The confidence model uses distance to the nearest tower and remoteness, and the plan named no source for either.

## Decision

- Tower locations come from OpenCelliD (an open database of cell tower locations), to compute the distance to the nearest tower.
- OpenCelliD is share-alike, so derived data carries the same license. This is recorded in the license register and on the page.
- Remoteness is the distance to the nearest road or trailhead, from published data; the source is set by ADR 0035 (TIGER/Line roads and NPS trail lines).

## Alternatives considered

- No other tower source is recorded.

## Consequences

- A source contract for OpenCelliD exists (contracts/opencellid_towers.yaml, draft).
- Share-alike also applies to published confidence values that use tower distance, in addition to the Ookla license (ADR 0013).
- The remoteness source is decided in ADR 0035 (OQ-18). Still open: the exact OpenCelliD attribution text and terms (OQ-22), and its fields (OQ-20).
