# 0009. Lake tables are Iceberg on S3, catalogued by AWS Glue

- Status: Accepted. Decided by the build plan (BP, "One tool per job": "Lake tables and catalog"); recorded with John's approval of the one-tool-per-job table, Oct 9, 2026.
- Date: Oct 9, 2026.

## Context

Every engine (Spark, DuckDB, Snowflake) must read the same tables without copies. Tables must allow history partitions and safe overwrites (BP rules 3, 7 and 8).

## Decision

Lake tables are Apache Iceberg tables on S3. The AWS Glue Data Catalog lists them. Spark writes them, DuckDB and Snowflake read them through Glue. Maintenance (compaction, expiring snapshots, removing orphan files) is the last task of the nightly run (BP rule 7).

## Alternatives considered

- Plain Parquet folders without a table format: rejected. No safe overwrite of one partition and no catalog for the other engines.
- Delta Lake: not chosen in the plan. The build plan names Iceberg for every engine.

## Consequences

- History is kept in partitions and rows, not in Iceberg snapshots, because snapshot expiry deletes old versions (BP rule 8).
- Glue is free for the first million objects and requests a month (BP, "Where each job runs").
- Links: [ADR-0005](0005-snowflake-single-warehouse-through-glue.md); [ADR-0019](0019-raw-data-immutable-and-storage-rules.md).
