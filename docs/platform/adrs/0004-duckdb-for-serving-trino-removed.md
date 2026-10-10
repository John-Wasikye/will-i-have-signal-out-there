# 0004. DuckDB serves queries in Lambda and on the box; Trino is removed

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Duplicate engines" and "Serving queries"; BP "Serving engine: Decided").
- Date: Oct 9, 2026.

## Context

Sites, APIs and agents read published tables. Trino is a cluster query engine that would duplicate DuckDB on one box (BP, "One tool per job").

## Decision

DuckDB serves queries. It runs in Lambda behind API Gateway and on the session box. There is no server, nothing is billed when idle, and it is fast at the sizes being served (BPD).

## Alternatives considered

- Trino: removed. It needs a cluster, which is not justified at these sizes.
- A managed warehouse for serving: rejected. It bills while idle, which would break the budget (ADR-0013).

## Consequences

- Serving depends on published Parquet files in S3, so each project publishes gold tables before a site reads them (BP 0.4).
- The serving template (ADR-0026) is the single pattern every project reuses.
- Links: [ADR-0026](0026-serving-template-and-cold-start-notice.md).
