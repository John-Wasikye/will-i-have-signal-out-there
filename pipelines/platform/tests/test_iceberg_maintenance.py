"""Tests for Iceberg maintenance, using a fake Spark session that records SQL.

The maintenance task runs last in every nightly run (engineering standard 7). For each
table it compacts small files, expires old snapshots, and removes orphan files. The
retention values here are defaults until OQ-P07 is answered by John after the first
table sizes are measured.
"""

from datetime import UTC, datetime, timedelta

import pytest
from iceberg_maintenance import (
    DEFAULT_ORPHAN_AGE_DAYS,
    DEFAULT_SNAPSHOT_RETENTION_DAYS,
    maintain_tables,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
NAMESPACE = "portfolio_dev"


class FakeSpark:
    def __init__(self):
        self.statements: list[str] = []

    def sql(self, statement: str) -> None:
        self.statements.append(statement)


def test_each_table_gets_compaction_snapshot_expiry_and_orphan_removal():
    spark = FakeSpark()
    maintain_tables(spark, ["sample_answer"], NOW, namespace=NAMESPACE)

    snapshot_cutoff = NOW - timedelta(days=DEFAULT_SNAPSHOT_RETENTION_DAYS)
    orphan_cutoff = NOW - timedelta(days=DEFAULT_ORPHAN_AGE_DAYS)
    table = "portfolio.portfolio_dev.sample_answer"
    assert spark.statements == [
        f"CALL portfolio.system.rewrite_data_files(table => '{table}')",
        f"CALL portfolio.system.expire_snapshots(table => '{table}', "
        f"older_than => TIMESTAMP '{snapshot_cutoff:%Y-%m-%d %H:%M:%S}')",
        f"CALL portfolio.system.remove_orphan_files(table => '{table}', "
        f"older_than => TIMESTAMP '{orphan_cutoff:%Y-%m-%d %H:%M:%S}')",
    ]


def test_maintenance_runs_for_every_table_in_order():
    spark = FakeSpark()
    maintain_tables(spark, ["a_table", "b_table"], NOW, namespace=NAMESPACE)
    tables_in_order = [
        statement.split("table => '")[1].split("'")[0] for statement in spark.statements
    ]
    assert tables_in_order == [
        "portfolio.portfolio_dev.a_table",
        "portfolio.portfolio_dev.a_table",
        "portfolio.portfolio_dev.a_table",
        "portfolio.portfolio_dev.b_table",
        "portfolio.portfolio_dev.b_table",
        "portfolio.portfolio_dev.b_table",
    ]


def test_table_names_are_checked_before_any_sql_runs():
    spark = FakeSpark()
    with pytest.raises(ValueError, match="must be lowercase"):
        maintain_tables(spark, ["bad; DROP TABLE x"], NOW, namespace=NAMESPACE)
    assert spark.statements == []


def test_naive_time_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        maintain_tables(
            FakeSpark(), ["sample_answer"], datetime(2026, 10, 9, 12, 0), namespace=NAMESPACE
        )


def test_the_namespace_is_checked_before_any_sql_runs():
    spark = FakeSpark()
    with pytest.raises(ValueError, match="must be lowercase"):
        maintain_tables(spark, ["sample_answer"], NOW, namespace="x; DROP TABLE y")
    assert spark.statements == []
