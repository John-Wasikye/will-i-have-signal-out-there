"""Write rows to an Iceberg table as the run date's partition.

The partition is the run's logical date, never the current time (engineering standard 3), so a
rerun of the same night replaces only that night's rows. The first write creates the table.
"""

from __future__ import annotations

from datetime import date

from sample_iceberg_job import CATALOG_NAME


def write_run_partition(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    table_name: str,
    rows: list[dict],
    run_date: date,
    *,
    namespace: str,
) -> int:
    """Write the rows as ``run_date``'s partition of the table and return the row count."""
    if not rows:
        raise ValueError(f"{table_name}: no rows to load; an empty pull must stop before this step")
    frame = spark.createDataFrame([row | {"run_date": run_date} for row in rows])
    full_name = f"{CATALOG_NAME}.{namespace}.{table_name}"
    if spark.catalog.tableExists(full_name):
        frame.writeTo(full_name).overwritePartitions()
    else:
        frame.writeTo(full_name).partitionedBy("run_date").create()
    return len(rows)
