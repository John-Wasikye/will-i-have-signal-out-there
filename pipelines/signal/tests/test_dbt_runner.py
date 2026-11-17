"""Tests for how the nightly run starts dbt (C7). No test here runs dbt itself."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dbt_runner import DBT_TIMEOUT_SECONDS, DbtBuildFailed, run_dbt

LOADED_AT = datetime(2026, 11, 4, 10, 2, tzinfo=UTC)


class Recorder:
    """Stands in for subprocess.run and keeps what it was asked to run."""

    def __init__(self, returncode=0, stdout=""):
        self.returncode, self.stdout = returncode, stdout
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, self.returncode, stdout=self.stdout)


def _run(tmp_path: Path, runner) -> None:
    run_dbt(
        dbt_bin=Path("/opt/dbt/bin/dbt"),
        project_dir=Path("/project"),
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "marts",
        work_dir=tmp_path / "work",
        loaded_at_utc=LOADED_AT,
        runner=runner,
    )


def test_dbt_gets_its_folders_and_the_load_time(tmp_path):
    runner = Recorder()
    _run(tmp_path, runner)
    ((command, kwargs),) = runner.calls
    assert command[1] == "build"
    assert "2026-11-04T10:02:00+00:00" in command[command.index("--vars") + 1]
    env = kwargs["env"]
    assert env["SIGNAL_DBT_INPUT_DIR"] == (tmp_path / "input").as_posix()
    assert env["SIGNAL_DBT_OUTPUT_DIR"] == (tmp_path / "marts").as_posix()
    assert env["SIGNAL_DBT_WORK_DIR"] == (tmp_path / "work").as_posix()
    assert env["DBT_PROFILES_DIR"] == Path("/project").as_posix()
    assert kwargs["timeout"] == DBT_TIMEOUT_SECONDS


def test_dbt_output_stays_out_of_the_project_folder(tmp_path):
    runner = Recorder()
    _run(tmp_path, runner)
    env = runner.calls[0][1]["env"]
    assert env["DBT_TARGET_PATH"].startswith((tmp_path / "work").as_posix())
    assert env["DBT_LOG_PATH"].startswith((tmp_path / "work").as_posix())


def test_a_retry_starts_from_empty_folders(tmp_path):
    for folder, name in ((tmp_path / "marts", "old.parquet"), (tmp_path / "work", "signal.duckdb")):
        folder.mkdir()
        (folder / name).write_text("left by the last try", encoding="utf-8")
    _run(tmp_path, Recorder())
    assert list((tmp_path / "marts").iterdir()) == []
    assert list((tmp_path / "work").iterdir()) == []


def test_a_failed_build_stops_the_run_and_says_why(tmp_path):
    with pytest.raises(DbtBuildFailed, match="unique_fct_satellite_window"):
        _run(tmp_path, Recorder(returncode=1, stdout="FAIL 1 unique_fct_satellite_window\n"))


# The real output of the failed build of Nov 14, 2026, shortened: passing tests, then dbt's summary.
PASSING = [
    f"\x1b[0m10:10:41  {n} of 52 PASS not_null_dim_trail_point_{n} [\x1b[32mPASS\x1b[0m in 0.02s]"
    for n in range(1, 52)
]
FAILED_TEST = "unique_columns_fct_reachable_period_trail_point_id__period_start_utc"
SUMMARY = [
    "\x1b[0m10:10:41  Finished running 6 external models, 42 data tests in 5.98 seconds.",
    "\x1b[0m10:10:41  ",
    "\x1b[0m10:10:41  \x1b[31mCompleted with 1 error, 0 partial successes, and 0 warnings:\x1b[0m",
    "\x1b[0m10:10:41  ",
    f"\x1b[0m10:10:41  \x1b[31mFailure in test {FAILED_TEST} (models/marts/marts.yml)\x1b[0m",
    "\x1b[0m10:10:41    Got 2 results, configured to fail if != 0",
    "\x1b[0m10:10:41  ",
    "\x1b[0m10:10:41  Done. PASS=51 WARN=0 ERROR=1 SKIP=0 TOTAL=52",
]


def _failure_text(tmp_path, lines) -> str:
    with pytest.raises(DbtBuildFailed) as caught:
        _run(tmp_path, Recorder(returncode=1, stdout="\n".join(lines) + "\n"))
    return str(caught.value)


def test_the_failure_text_starts_with_what_failed_so_a_cut_alert_still_says_it(tmp_path):
    text = _failure_text(tmp_path, PASSING + SUMMARY)
    # The alert email and the incident record keep only the first 300 characters.
    assert f"Failure in test {FAILED_TEST}" in text[:300]
    assert "Got 2 results" in text[:300]


def test_the_failure_text_has_no_colour_codes(tmp_path):
    assert "\x1b" not in _failure_text(tmp_path, PASSING + SUMMARY)


def test_the_lines_before_the_summary_follow_it(tmp_path):
    text = _failure_text(tmp_path, PASSING + SUMMARY)
    assert text.index("Completed with 1 error") < text.index("51 of 52 PASS")


def test_output_without_a_summary_keeps_its_last_lines(tmp_path):
    text = _failure_text(tmp_path, ["Compilation Error", "  model x depends on a missing node"])
    assert text.endswith("Compilation Error\n  model x depends on a missing node")
