"""Iceberg maintenance: the last task of every nightly run (engineering standard 7).

For each table, in order:
1. rewrite_data_files merges small files so reads stay fast.
2. expire_snapshots removes snapshots older than the retention window.
3. remove_orphan_files deletes files that no snapshot points to.

The default windows are placeholders until John sets them after measuring table sizes
(open question OQ-P07).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from publish import TABLE_NAME
from timeutil import require_utc

CATALOG_NAME = "portfolio"
DEFAULT_SNAPSHOT_RETENTION_DAYS = 7
DEFAULT_ORPHAN_AGE_DAYS = 3


def maintain_tables(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    table_names: list[str],
    now_utc: datetime,
    snapshot_retention_days: int = DEFAULT_SNAPSHOT_RETENTION_DAYS,
    orphan_age_days: int = DEFAULT_ORPHAN_AGE_DAYS,
) -> None:
    """Run the three maintenance steps for each table, in the order listed above.

    Every table name is checked before the first statement runs, so one bad name stops the
    whole task without changing any table.
    """
    now_utc = require_utc(now_utc, "now_utc")
    for name in table_names:
        if not TABLE_NAME.match(name):
            raise ValueError(f"table name {name!r} must be lowercase letters, digits and _")

    snapshot_cutoff = _sql_timestamp(now_utc - timedelta(days=snapshot_retention_days))
    orphan_cutoff = _sql_timestamp(now_utc - timedelta(days=orphan_age_days))
    for name in table_names:
        full_name = f"{CATALOG_NAME}.{name}"
        spark.sql(f"CALL {CATALOG_NAME}.system.rewrite_data_files(table => '{full_name}')")
        spark.sql(
            f"CALL {CATALOG_NAME}.system.expire_snapshots("
            f"table => '{full_name}', older_than => TIMESTAMP '{snapshot_cutoff}')"
        )
        spark.sql(
            f"CALL {CATALOG_NAME}.system.remove_orphan_files("
            f"table => '{full_name}', older_than => TIMESTAMP '{orphan_cutoff}')"
        )


def _sql_timestamp(moment: datetime) -> str:
    """Format a UTC moment as the literal text Spark SQL expects."""
    return moment.strftime("%Y-%m-%d %H:%M:%S")
