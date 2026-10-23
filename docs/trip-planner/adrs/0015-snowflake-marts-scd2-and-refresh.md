# 0015. Run Project 1 marts on Snowflake over Glue, with SCD Type 2 coverage history and a refresh step

- Status: Accepted (John, Build Plan Decisions, Oct 9, 2026)
- Date: Oct 9, 2026
- Source: Build Plan Decisions "Warehouse" and "Snowflake"; build plan 1B.3; engineering standard 8 (keep business history in rows, not snapshots)

## Context

Snowflake is the one data warehouse. It reads Iceberg tables in place through the AWS Glue catalog (a registry of tables), so no data is copied. FCC coverage changes between releases and business history must live in rows, not in Iceberg snapshots (snapshot expiry deletes old versions).

## Decision

- Snowflake reads Iceberg through the Glue catalog; a refresh step runs at the end of each pipeline run so Snowflake sees new data.
- The dbt marts (finished tables built by dbt) run on Snowflake, with SCD Type 2 rows (history kept as rows with validity ranges) for carrier coverage changes between FCC releases.
- Metrics are defined in MetricFlow; one metric must give the same value from Snowflake and from DuckDB.
- A resource monitor suspends the warehouse at 3 credits a month (about $6 after the trial) and every query has a time limit. The 30-day trial with $400 of credits starts in Phase B step 1B.3.

## Alternatives considered

- BigQuery as a warehouse: removed as a duplicate.
- No other alternatives are recorded.

## Consequences

- If the Glue connection or refresh does not work as expected, the warehouse stays stale; the first-run check is OQ-4. Snowflake's docs list no edition requirement for the Glue connection; check in 1B.3.
- The site never reads Snowflake; it reads published Parquet through DuckDB.
- SCD Type 2 history depends on FCC release versions being identifiable (OQ-20).
