# 0024. Every pipeline reports freshness and row counts; a status page shows the last good run; one incident record and one GitHub issue per real incident

- Status: Accepted. Decided by the build plan (BP rule 11, step 0.5; step 1B.9 for GitHub issues) and John's acceptance, Oct 9, 2026. The alert threshold numbers are set per project.
- Date: Oct 9, 2026.

## Context

Problems must surface before users see them (BP rule 11). Real incidents become the test set for the on-call agent later (BP, "Testing").

## Decision

1. Every DAG writes freshness and row counts to a metrics table (contracts/platform_run_metrics.yaml).
2. A small job publishes `status.json` for the status page, which shows each pipeline's last good run.
3. A missed freshness target or a failed run sends an email (step 0.5).
4. Each real incident gets a short record: what broke, the cause and the fix. From step 1B.9, a failed run also opens one GitHub issue, with no duplicates, and the issue closes on recovery.
5. Real incidents are not staged (BPD, "Failure testing").

Defaults pending John's approval (OQ-P01): email goes through an SNS topic with John's address as subscriber; the metrics table is an Iceberg table in the lake; each incident record is the Iceberg table platform_incidents.

## Alternatives considered

- Email only, without a status page: rejected. Readers need the last good run visible.
- Paid monitoring service: not chosen. It bills while idle.

## Consequences

- The late-data notice on each project's site uses the last good run time (Project 1, ADR 0027).
- Links: [contracts/platform_run_metrics.yaml](../contracts/platform_run_metrics.yaml); [operations](../operations.md).
