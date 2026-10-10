# 0027. Every paid job has a hard maximum for rows and runtime, set from a measured size estimate

- Status: Accepted. Decided by the build plan (BP, "Hard limits on everything that costs money") and John's acceptance, Oct 9, 2026. The numbers are not set yet; each project sets its own once measured.
- Date: Oct 9, 2026.

## Context

"Nothing in the project should surprise with cost" (BPD, "Surprise costs"). A Spark job that grows past its expected size can run up cost.

## Decision

1. Each Spark job has a maximum number of rows read and written, and a maximum runtime. A job over either limit stops before publishing and opens an incident.
2. Limits are set from a measured size estimate written in the project's design doc, before the first build step that uses the data (BP).
3. The same rule applies to servers (session limit, 4 hours), GPU hours (Project 5, spot only), Snowflake (3 credits a month, a time limit per query), the public API (a cap on copies running at once and per-key quotas), the model (ADR-0014), storage (ADR-0019) and DynamoDB (provisioned within the free tier).

## Alternatives considered

- Limits guessed before measuring: rejected by John's "no guesses" rule (BPD, "No guesses").

## Consequences

- Each project's design doc holds its measured numbers (BP rule 12, design note per project).
- Links: [ADR-0013](0013-cost-guards-and-spend-limits.md); [operations](../operations.md).
