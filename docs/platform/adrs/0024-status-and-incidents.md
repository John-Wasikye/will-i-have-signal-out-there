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

## Update, Oct 28, 2026: where incident records live, and how they close

Each incident record is one Parquet file in the lake bucket, under `platform/incidents/`. That copy is the record:

- A new incident is filed in S3 as soon as it opens, by the failure callback or by the watchdog. Its number is one more than the highest used that day in S3 or on the box, so a replaced box never reuses a number.
- An upload never replaces a record S3 already has. Every incident write uses a conditional write (If-None-Match), so the nightly upload only adds records that S3 lacks.
- I close a record with `python pipelines/platform/publish/incidents.py close`, which writes the cause, the fix and the close time. The write uses If-Match, so a record changed in the meantime is never overwritten, and the bucket's versions keep the open record.

Why: on Oct 27, 2026 I found that the nightly upload copied the box's files over S3, so a record closed in S3 went back to open the next night, and a replaced box restarted its numbering at 01 and could overwrite a different record. The contract still names an Iceberg table; the records are Parquet files until a reader needs the table.

## Alternatives considered

- Email only, without a status page: rejected. Readers need the last good run visible.
- Paid monitoring service: not chosen. It bills while idle.

## Consequences

- The late-data notice on each project's site uses the last good run time (Project 1, ADR 0027).
- Links: [contracts/platform_run_metrics.yaml](../contracts/platform_run_metrics.yaml); [operations](../operations.md).
