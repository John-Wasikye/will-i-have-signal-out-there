"""Start ``dbt build`` as its own program (C7).

dbt has its own Python environment, because Airflow's pinned packages refuse it (``pathspec`` is
the hard clash). So the nightly run starts it as a separate program and reads its exit code. dbt
reads the Parquet copies in ``input_dir``, keeps its working files in ``work_dir``, and writes one
Parquet file per mart to ``output_dir``. A failed model or test stops the run before the gate.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DBT_TIMEOUT_SECONDS = 900
FAILURE_LINES_KEPT = 40


class DbtBuildFailed(RuntimeError):
    """A dbt model or test failed, so nothing built tonight may be published."""


def run_dbt(
    *,
    dbt_bin: Path,
    project_dir: Path,
    input_dir: Path,
    output_dir: Path,
    work_dir: Path,
    loaded_at_utc: datetime,
    runner: Callable = subprocess.run,
) -> None:
    """Build and test every model from empty folders, or raise ``DbtBuildFailed``."""
    for folder in (output_dir, work_dir):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    env = {
        **os.environ,
        "DBT_PROFILES_DIR": project_dir.as_posix(),
        "DBT_TARGET_PATH": (work_dir / "target").as_posix(),
        "DBT_LOG_PATH": (work_dir / "logs").as_posix(),
        "SIGNAL_DBT_INPUT_DIR": input_dir.as_posix(),
        "SIGNAL_DBT_OUTPUT_DIR": output_dir.as_posix(),
        "SIGNAL_DBT_WORK_DIR": work_dir.as_posix(),
    }
    result = runner(
        [
            str(dbt_bin),
            "build",
            "--project-dir",
            project_dir.as_posix(),
            "--vars",
            json.dumps({"loaded_at_utc": loaded_at_utc.isoformat()}),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=DBT_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-FAILURE_LINES_KEPT:])
        raise DbtBuildFailed(f"dbt build failed with exit code {result.returncode}:\n{tail}")
