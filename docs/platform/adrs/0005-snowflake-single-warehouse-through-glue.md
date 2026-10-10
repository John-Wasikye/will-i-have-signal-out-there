# 0005. Snowflake is the one warehouse, reading Iceberg through the Glue catalog; BigQuery is not used

- Status: Accepted. Decided by John, Oct 9, 2026 (BPD, "Warehouse"; BP "Warehouse: Decided").
- Date: Oct 9, 2026.

## Context

Marts, dashboards and metric definitions need one warehouse. Snowflake reads the Iceberg tables in place through the Glue catalog, so there are no copies (BPD).

## Decision

Snowflake is the one warehouse. It reads Iceberg tables through the AWS Glue catalog. dbt builds the marts, with MetricFlow for metric definitions. The trial is 30 days with $400 of credits, started in Project 1 Phase B. After the trial it is an X-Small warehouse with a 60-second auto-suspend and a resource monitor at 3 credits a month (ADR-0013).

## Alternatives considered

- BigQuery: removed as a duplicate warehouse.

## Consequences

- Each Snowflake refresh runs after each pipeline run, so Snowflake sees new data (BP, "Snowflake setup"). The check is in step 1B.3.
- The Glue connection needs no particular edition, but the basic connection requires the refresh step (BP, "Snowflake setup").
- Links: [ADR-0013](0013-cost-guards-and-spend-limits.md); [ADR-0009](0009-iceberg-tables-with-glue-catalog.md).
