"""Tests for install.sh, the script that sets up the session box.

I run the script in dry-run mode. It prints each step and each command but runs none of
them, so the tests can check the order of the steps and what the commands contain without
touching a real machine.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "install.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not available here")

REQUIRED_SETTINGS = {
    "IMAGE_REPOSITORY": "123456789012.dkr.ecr.us-east-1.amazonaws.com/portfolio-airflow",
    "IMAGE_TAG": "3.3.2",
    "BACKUP_BUCKET": "portfolio-dev-lake-123456789012",
}


def _run(arguments: list[str], settings: dict[str, str] | None = None):
    environment = {**os.environ, "DRY_RUN": "1"}
    for name in REQUIRED_SETTINGS:
        environment.pop(name, None)
    environment.update(REQUIRED_SETTINGS if settings is None else settings)
    return subprocess.run(
        [BASH, str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def _steps(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("STEP ")]


def test_the_script_asks_for_an_environment():
    result = _run([])

    assert result.returncode == 2
    assert "usage" in result.stderr.lower()


def test_an_unknown_environment_is_refused():
    result = _run(["staging"])

    assert result.returncode == 2
    assert "dev or live" in result.stderr


@pytest.mark.parametrize("missing", sorted(REQUIRED_SETTINGS))
def test_a_missing_setting_is_named_in_the_error(missing):
    settings = {k: v for k, v in REQUIRED_SETTINGS.items() if k != missing}

    result = _run(["dev"], settings=settings)

    assert result.returncode == 2
    assert missing in result.stderr


def test_the_steps_run_in_a_safe_order():
    result = _run(["dev"])

    assert result.returncode == 0, result.stderr
    names = [step.split(": ", 1)[1] for step in _steps(result.stdout)]
    assert names == [
        "install k3s",
        "install helm",
        "create the airflow namespace",
        "create the database secrets from Parameter Store",
        "install airflow",
        "restore the database backup",
        "restart airflow",
    ]


def test_k3s_helm_and_the_chart_are_pinned_to_exact_versions():
    output = _run(["dev"]).stdout

    assert "INSTALL_K3S_VERSION=v1.36.5+k3s1" in output
    assert "DESIRED_VERSION=v4.3.0" in output
    assert "--version 1.22.0" in output


def test_dev_uses_only_the_base_settings_file():
    output = _run(["dev"]).stdout

    assert "airflow-values.yaml" in output
    assert "airflow-values-live.yaml" not in output


def test_live_adds_the_live_settings_file():
    output = _run(["live"], settings={**REQUIRED_SETTINGS, "BACKUP_BUCKET": "b"}).stdout

    assert "airflow-values.yaml" in output
    assert "airflow-values-live.yaml" in output


def test_the_image_comes_from_the_settings():
    output = _run(["dev"]).stdout

    assert f"images.airflow.repository={REQUIRED_SETTINGS['IMAGE_REPOSITORY']}" in output
    assert f"images.airflow.tag={REQUIRED_SETTINGS['IMAGE_TAG']}" in output


def test_the_database_password_is_read_from_parameter_store_and_never_written_out():
    output = _run(["dev"]).stdout

    assert "/portfolio/dev/platform/airflow-db-password" in output
    assert "--with-decryption" in output
    assert "--from-literal" not in output
    assert "stringData" not in output


def test_the_backup_is_restored_after_airflow_is_installed_and_before_it_restarts():
    output = _run(["dev"]).stdout

    install = output.index("STEP 5")
    restore = output.index("STEP 6")
    restart = output.index("STEP 7")
    assert install < restore < restart
    assert "airflow_db_backup.py restore --bucket portfolio-dev-lake-123456789012" in output


def test_the_script_stops_at_the_first_failing_step(tmp_path):
    text = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
