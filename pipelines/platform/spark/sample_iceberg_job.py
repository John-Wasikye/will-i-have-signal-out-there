"""Spark job: write the sample rows to an Iceberg table.

Rules followed (docs/platform/design-doc.md, section 12 and engineering standards):
- Overwrite one partition per run, never blind-append, so a rerun gives the same rows.
- A row limit is checked before anything is written; a job over the limit stops.
- Timestamps come from the run's data interval, never from now() inside the job.

The Spark session is created by the caller. Dev uses a local Hadoop catalog. The
box and CI use the AWS Glue catalog through the Iceberg Spark runtime.
"""

from __future__ import annotations

from datetime import date, datetime

from sample_rows import build_sample_rows

ICEBERG_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1"
CATALOG_NAME = "portfolio"


class RowLimitExceeded(RuntimeError):
    """Raised before writing when the job would read or write too many rows."""


def build_spark_session(app_name: str, warehouse: str, use_glue: bool = False):  # noqa: ANN201
    """Create a SparkSession configured for Iceberg.

    ``warehouse`` is a local path for dev, or an S3 URI for the Glue catalog.
    Import pyspark here so the rest of this module imports without Spark installed.
    """
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.jars.packages", ICEBERG_PACKAGE)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config(f"spark.sql.catalog.{CATALOG_NAME}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{CATALOG_NAME}.warehouse", warehouse)
    )
    if use_glue:
        builder = builder.config(
            f"spark.sql.catalog.{CATALOG_NAME}.catalog-impl",
            "org.apache.iceberg.aws.glue.GlueCatalog",
        ).config(
            f"spark.sql.catalog.{CATALOG_NAME}.io-impl",
            "org.apache.iceberg.aws.s3.S3FileIO",
        )
    else:
        builder = builder.config(f"spark.sql.catalog.{CATALOG_NAME}.type", "hadoop")
    return builder.getOrCreate()


def run_sample_iceberg_job(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    table_name: str,
    run_date: date,
    now_utc: datetime,
    max_rows: int,
) -> int:
    """Write one partition of the sample table and return the number of rows written.

    The table is partitioned by ``run_date``. Only that day's partition is replaced.
    """
    rows = build_sample_rows(now_utc, run_date)
    if len(rows) > max_rows:
        raise RowLimitExceeded(f"{len(rows)} rows is over the limit of {max_rows}")

    frame = spark.createDataFrame(rows)
    full_name = f"{CATALOG_NAME}.{table_name}"
    if spark.catalog.tableExists(full_name):
        frame.writeTo(full_name).overwritePartitions()
    else:
        frame.writeTo(full_name).partitionedBy("run_date").create()
    return frame.count()
