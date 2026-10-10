# 0028. Every source has a data contract and the schema is diffed before loading; a weekly test pull checks each source

- Status: Accepted. Decided by the build plan (BP rule 5) and John's answer in BPD, "Source changes": "Data contracts plus a weekly test pull from every source (A + B)". The weekly test is added in step 1B.9.
- Date: Oct 9, 2026.

## Context

An upstream change should fail loudly and early (BP rule 5). A format change should be caught before the nightly run fails (BPD, "Source changes").

## Decision

1. Each source has a data contract with its schema, rules, freshness target, owner and version (ODCS format, BP rule 5).
2. The schema is diffed against the contract before each load. A difference stops the load and raises an incident.
3. A weekly test pull from each source (step 1B.9) checks the format. The check is part of the platform's source checks.

## Alternatives considered

- Check only when a run fails: rejected by John (BPD, "Source changes").

## Consequences

- Contracts follow ODCS v3.x as a working choice. The version is pinned per project (each project pins its own version).
- Links: [ADR-0024](0024-status-and-incidents.md).
