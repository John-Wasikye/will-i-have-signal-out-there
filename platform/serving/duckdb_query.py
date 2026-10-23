"""Run read-only DuckDB queries over published Parquet files.

The serving template reads only published files, so a request works with the
session box switched off (ADR-0011, ADR-0026).
"""

from __future__ import annotations

from typing import Any

import duckdb


def query_rows(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run one query and return its rows as dictionaries keyed by column name.

    The SQL text is fixed by the caller. Values from requests go in ``params``
    only, never into the SQL string.
    """
    connection = duckdb.connect(database=":memory:")
    try:
        result = connection.execute(sql, params or [])
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()
