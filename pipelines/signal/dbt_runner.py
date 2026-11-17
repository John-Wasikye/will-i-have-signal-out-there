"""Start ``dbt build`` as its own program (C7).

dbt has its own Python environment, because Airflow's pinned packages refuse it (``pathspec`` is
the hard clash). So the nightly run starts it as a separate program and reads its exit code. dbt
reads the Parquet copies in ``input_dir``, keeps its working files in ``work_dir``, and writes one
Parquet file per mart to ``output_dir``. A failed model or test stops the run before the gate.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DBT_TIMEOUT_SECONDS = 900
FAILURE_LINES_KEPT = 40
SUMMARY_START = "Completed with"  # dbt lists what failed from this line on
_COLOUR_CODE = re.compile(r"\x1b\[[0-9;]*m")
_ONLY_A_TIME = re.compile(r"\s*(\d\d:\d\d:\d\d)?\s*")


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
        raise DbtBuildFailed(
            f"dbt build failed with exit code {result.returncode}:\n{failure_text(result.stdout)}"
        )


def failure_text(output: str) -> str:
    """Return the last lines of dbt's output, with its summary of what failed moved to the top.

    The alert email and the incident record keep only the start of an error, and dbt prints what
    failed at the very end, so without the move they showed passing tests only. Colour codes and
    lines that hold only a time are left out.
    """
    plain = _COLOUR_CODE.sub("", output).splitlines()
    lines = [line for line in plain if not _ONLY_A_TIME.fullmatch(line)][-FAILURE_LINES_KEPT:]
    starts = [i for i, line in enumerate(lines) if SUMMARY_START in line]
    if starts:
        lines = lines[starts[-1] :] + lines[: starts[-1]]
    return "\n".join(lines)
