"""Publish gate: checks that run on staged data before anything goes live.

This is the audit step of write, audit, publish (engineering standard 4). A
failed check stops publishing. Each check returns a failure message, or None
when it passes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    """Outcome of all checks on one publish attempt."""

    passed: bool
    failures: tuple[str, ...] = ()


def check_not_empty(table_name: str, row_count: int) -> str | None:
    """Fail when a table has no rows."""
    if row_count == 0:
        return f"{table_name}: no rows"
    return None


def check_row_limit(table_name: str, row_count: int, max_rows: int) -> str | None:
    """Fail when a table is larger than its row limit (BD Surprise costs)."""
    if row_count > max_rows:
        return f"{table_name}: {row_count} rows is over the limit of {max_rows}"
    return None


def evaluate(checks: Iterable[str | None]) -> GateResult:
    """Combine check results into one gate result."""
    failures = tuple(message for message in checks if message is not None)
    return GateResult(passed=not failures, failures=failures)
