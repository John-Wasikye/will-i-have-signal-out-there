"""Publish step: write gold tables as Parquet, only after the gate passes.

Files are written to a staging folder first, then moved into place with
os.replace, which is atomic on one filesystem. Readers never see a half-written
file (write, audit, publish; engineering standard 4).
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from gate import GateResult

TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_STAGING_DIR = ".staging"


class PublishRefused(RuntimeError):
    """Raised when publishing is attempted without a passing gate."""


def publish_tables(
    tables: Mapping[str, pa.Table],
    gate: GateResult,
    published_dir: Path,
) -> list[Path]:
    """Write each table to ``published_dir/<name>.parquet`` and return the paths.

    Raises PublishRefused when the gate did not pass, so a failed check never
    reaches readers.
    """
    if not gate.passed:
        raise PublishRefused("publish refused: " + "; ".join(gate.failures))

    for name in tables:
        if not TABLE_NAME.match(name):
            raise ValueError(f"table name {name!r} must be lowercase letters, digits and _")

    published_dir.mkdir(parents=True, exist_ok=True)
    staging = published_dir / _STAGING_DIR
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()

    try:
        staged: dict[str, Path] = {}
        for name, table in tables.items():
            target = staging / f"{name}.parquet"
            pq.write_table(table, target, compression="zstd")
            staged[name] = target

        published: list[Path] = []
        for name, staged_file in staged.items():
            destination = published_dir / f"{name}.parquet"
            os.replace(staged_file, destination)
            published.append(destination)
        return published
    finally:
        shutil.rmtree(staging, ignore_errors=True)
