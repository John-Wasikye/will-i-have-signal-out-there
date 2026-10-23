# 0018. Data contracts for every source and published table, plus a weekly test pull from every source

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026; contracts in Phase A, weekly pull from step 1B.9)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Source changes" and "Extras moved later"; build plan 1A.5, 1B.9; engineering standard 5 (a contract per source, schema diffed before loading); Documentation Plan "Interface specs"

## Context

Upstream sources change format without notice. A change should fail loudly and early, before the nightly run fails.

## Decision

- Each source has a contract with schema, rules, freshness target, owner and version (engineering standard 5), written in the Open Data Contract Standard (ODCS, a YAML format for data contracts). The schema is diffed before loading.
- Contracts exist from Phase A for CelesTrak, FCC, NPS trails and elevation.
- A weekly smoke test pulls one small sample from every source the project uses and alerts on any format change (step 1B.9).

Reason recorded by John: it catches format changes before the nightly run fails. The weekly test was moved to step 1B.9 so the first live page goes up sooner.

## Alternatives considered

- None recorded.

## Consequences

- Contract files live in `contracts/` and are checked in CI against sample files.
- Until the first-run checks run, source URLs and field lists are drafts (OQ-20).
- The ODCS version is pinned in ADR 0032 (OQ-32).
