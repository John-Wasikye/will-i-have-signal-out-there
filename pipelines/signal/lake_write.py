"""Write rows to an Iceberg table as the run date's partition, with the table's declared types.

The partition is the run's logical date, never the current time (engineering standard 3), so a
rerun of the same night replaces only that night's rows. The first write creates the table.

Spark is always told each column's type, never left to guess it from the Python values. A guess
failed the live skeleton run on 2026-10-29 (INC-2026-10-29-01): Airflow's pendulum time came out
as an empty struct. Spark also cannot guess for a column that is None in every row, and it would
guess a whole-number "number" column as an integer one night and a double the next. The types
come from the table's data contract in docs/trip-planner/contracts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml
from sample_iceberg_job import CATALOG_NAME
from timeutil import require_utc

# Contract logical types (Open Data Contract Standard) and the Spark SQL type each one is stored as.
SPARK_TYPES = {
    "string": "STRING",
    "integer": "BIGINT",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
}


@dataclass(frozen=True)
class Column:
    """One column of a lake table: its name, contract logical type and whether it may be empty."""

    name: str
    logical_type: str
    required: bool


def contract_columns(contract_path: Path, table_name: str) -> tuple[Column, ...]:
    """Return the columns the contract declares for ``table_name``, in the contract's order."""
    contract = yaml.safe_load(Path(contract_path).read_text(encoding="utf-8"))
    for table in contract.get("schema", []):
        if table["name"] == table_name:
            return tuple(
                Column(column["name"], column["logicalType"], bool(column.get("required", False)))
                for column in table["properties"]
            )
    raise ValueError(f"{contract_path}: no table named {table_name}")


def spark_schema(columns: Sequence[Column]) -> str:
    """Return the Spark DDL schema for the columns plus the ``run_date`` partition column."""
    declared = []
    for column in columns:
        if column.logical_type not in SPARK_TYPES:
            raise ValueError(
                f"{column.name}: no Spark type for logical type {column.logical_type!r}"
            )
        not_null = " NOT NULL" if column.required else ""
        declared.append(f"{column.name} {SPARK_TYPES[column.logical_type]}{not_null}")
    declared.append("run_date DATE NOT NULL")
    return ", ".join(declared)


def conform_rows(rows: Sequence[dict], columns: Sequence[Column], run_date: date) -> list[dict]:
    """Check each row against the columns, give each value its declared Python type, add run_date.

    Spark refuses an int for a DOUBLE column and pendulum's subclasses for TIMESTAMP and DATE, so
    the values are converted here, where a wrong one gets a clear error with the column's name.
    """
    names = [column.name for column in columns]
    plain_run_date = date(run_date.year, run_date.month, run_date.day)
    conformed = []
    for row in rows:
        missing = [name for name in names if name not in row]
        unexpected = [name for name in row if name not in names]
        if missing or unexpected:
            raise ValueError(
                f"row does not match the table: missing {', '.join(missing) or 'none'}; "
                f"unexpected {', '.join(unexpected) or 'none'}"
            )
        values = {column.name: _conform_value(row[column.name], column) for column in columns}
        conformed.append(values | {"run_date": plain_run_date})
    return conformed


def _conform_value(value: object, column: Column) -> object:
    """Return the value as the plain Python type Spark accepts for the column."""
    if value is None:
        if column.required:
            raise ValueError(f"{column.name} is required but a row has no value")
        return None
    if column.logical_type == "number" and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if column.logical_type == "timestamp" and isinstance(value, datetime):
        return require_utc(value, column.name)
    return value


def write_run_partition(
    spark,  # noqa: ANN001, a pyspark SparkSession, typed loosely to avoid importing pyspark
    table_name: str,
    rows: list[dict],
    run_date: date,
    *,
    columns: Sequence[Column],
    namespace: str,
) -> int:
    """Write the rows as ``run_date``'s partition of the table and return the row count."""
    if not rows:
        raise ValueError(f"{table_name}: no rows to load; an empty pull must stop before this step")
    frame = spark.createDataFrame(
        conform_rows(rows, columns, run_date), schema=spark_schema(columns)
    )
    full_name = f"{CATALOG_NAME}.{namespace}.{table_name}"
    if spark.catalog.tableExists(full_name):
        frame.writeTo(full_name).overwritePartitions()
    else:
        frame.writeTo(full_name).partitionedBy("run_date").create()
    return len(rows)
