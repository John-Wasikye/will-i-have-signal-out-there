# 0020. Dev and live are fully separate; only merges to main reach live, and only after the changed pipelines pass on sample data

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Dev and live"; BP steps 0.1 and 0.2).
- Date: Oct 9, 2026.

## Context

A test run must never damage live data (BPD, "Dev and live"). Changes must be tested before they deploy (BP, "Automatic deploys, tested first").

## Decision

1. Dev and live have separate buckets, separate Glue databases, separate roles and separate SES identities and DynamoDB tables.
2. Dev roles cannot write to live data. A dev role's attempt to write live data is refused, and this is part of the step 0.2 done-when.
3. Only merges to main reach live. Before that, GitHub's free CI machines run the changed pipelines with Spark on sample data. If they pass, the change deploys to dev and then to live.
4. Every website change gets a preview link before it goes live (BP step 0.4).

## Alternatives considered

- A shared bucket with prefixes: rejected. One mistaken path would reach live data.
- Deploying straight to live: rejected by John's build method.

## Consequences

- Every project's first-run checks run in dev first.
- Dev data is deleted after 14 days (ADR-0019).
- Links: [ADR-0030](0030-tests-on-github-ci-then-dev-then-live.md).
