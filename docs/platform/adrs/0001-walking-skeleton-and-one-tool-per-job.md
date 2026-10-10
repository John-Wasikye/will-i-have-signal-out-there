# 0001. Build a walking skeleton first, and give each job exactly one tool

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Build approach and phasing" and "Tools and platform").
- Date: Oct 9, 2026.

## Context

Five projects are planned, each in three phases (BP, "How the plan works"). The platform has to exist before any project, and it has to keep a live site up while it grows. Duplicate tools that do the same job add cost and things to learn. John asked for the most efficient tool for each job and for duplicates to be removed (BPD, "Duplicate engines").

## Decision

1. The platform starts as a small version of the whole system. Every main part (scheduler, processing, storage, checks, serving, website) runs on Kubernetes and is connected end to end (BP, "Platform skeleton"). It then grows while it keeps running.
2. Each job has exactly one tool. The tool table is in the design doc, section 2 and the build plan's "One tool per job" table.
3. Removed duplicates: Trino, Flink, BigQuery, pgvector and DataHub (see ADR-0004, ADR-0005, ADR-0010, ADR-0016, ADR-0017).

## Alternatives considered

- Build each project end to end in turn without a shared platform: rejected. Each project would repeat the same setup and the site would have no live page until a whole project was done.
- Keep several engines for different sizes of work: rejected by John (BPD, "Duplicate engines").

## Consequences

- Platform pieces arrive when first needed, and each tool is set up once, in the first phase that uses it (BP, "When each tool is introduced").
- A tool that is added later must go through the same one-tool-per-job check before it is added.
- Links: [design doc](../design-doc.md) section 2.
