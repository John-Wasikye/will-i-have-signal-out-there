# 0010. Lineage uses OpenLineage with Marquez, from one pinned ARM build; DataHub is removed

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Lineage graph (Marquez)"; BP "Lineage and catalog"). The ARM build is not yet proven (open question OQ-P03).
- Date: Oct 9, 2026.

## Context

Lineage shows which table was built from which. Marquez, the lineage server, publishes only x86 images. The server runs on arm64 boxes (BP rule and "Use arm64 images"). DataHub was a duplicate catalog (BP, "One tool per job").

## Decision

1. Airflow and Spark send OpenLineage events to Marquez. dbt docs give the table catalog (BP, "Lineage and catalog").
2. John chose to build ARM images of one pinned Marquez version once, in GitHub Actions. The image is rebuilt only when John chooses to upgrade (BPD, "Lineage graph").
3. DataHub is removed.

## Alternatives considered

- Rebuild on every release: rejected by John as too much work.
- Use the x86 image on an x86 box: not chosen. The box is arm64.
- DataHub: removed as a duplicate.

## Consequences

- Whether the ARM build succeeds is not yet known. Project 1 Phase B runs it (Documentation Plan, "Questions still open"). If it fails, this record is revised.
- Marquez is Phase B work for Project 1 and is reused by later projects.
- Links: [ADR-0002](0002-k3s-on-the-session-box.md); design doc open question OQ-P03.
