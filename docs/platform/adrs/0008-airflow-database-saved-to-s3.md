# 0008. Airflow's database lives on the session box, saved to S3 after every run and restored at startup

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Airflow's database").
- Date: Oct 9, 2026.

## Context

Airflow keeps run history in a PostgreSQL database. The database is needed only while the box runs, and the pipelines are safe to rerun (BPD).

## Decision

1. Airflow's PostgreSQL database runs on the session box. Nothing else uses it.
2. It is saved to S3 after every run and at shutdown, and restored at startup.
3. Airflow reads its connection keys from Parameter Store, so the backup holds no key (ADR-0007).

## Alternatives considered

- A managed database for Airflow: not chosen. It would bill while idle.
- No backup: rejected. Run history would be lost at every shutdown.

## Consequences

- Airflow's run history survives a teardown (BP step 0.3 done-when).
- PostgreSQL is used for this job only, not for visitor data (ADR-0006).
- Links: [ADR-0002](0002-k3s-on-the-session-box.md); [ADR-0007](0007-keys-in-parameter-store.md).
