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


def _find_bash() -> str | None:
    """Return a bash that can read this machine's file paths, or None.

    On Windows, the first bash on PATH is often WSL's, which cannot read Windows paths. Git Bash
    can, and it sits in the bin folder of the Git install, next to git itself.
    """
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if git is None:
        return None
    for folder in Path(git).resolve().parents:
        candidate = folder / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return None


BASH = _find_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not available here")

REQUIRED_SETTINGS = {
    "IMAGE_REPOSITORY": "123456789012.dkr.ecr.us-east-1.amazonaws.com/portfolio-airflow",
    "IMAGE_TAG": "3.3.2",
    "BACKUP_BUCKET": "portfolio-dev-lake-123456789012",
    "SITE_BUCKET": "portfolio-dev-site-123456789012",
    "ALERT_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts",
}
LIVE_TOPIC = "arn:aws:sns:us-east-1:123456789012:portfolio-live-run-alerts"


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


def _section(output: str, name: str) -> str:
    """Return the text of one step: from its STEP line to the next STEP line."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("STEP ") and name in line)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("STEP ")), len(lines)
    )
    return os.linesep.join(lines[start:end])


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
        "install the python tools for the box scripts",
        "create the airflow namespace",
        "create the database secrets from Parameter Store",
        "create the platform settings",
        "install airflow",
        "restore the database backup",
        "restart airflow",
        "start the watchdog",
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
    output = _run(
        ["live"],
        settings={**REQUIRED_SETTINGS, "BACKUP_BUCKET": "b", "ALERT_TOPIC_ARN": LIVE_TOPIC},
    ).stdout

    assert "airflow-values.yaml" in output
    assert "airflow-values-live.yaml" in output


def test_the_image_comes_from_the_settings():
    output = _run(["dev"]).stdout

    assert f"images.airflow.repository={REQUIRED_SETTINGS['IMAGE_REPOSITORY']}" in output
    assert f"images.airflow.tag={REQUIRED_SETTINGS['IMAGE_TAG']}" in output


def test_the_database_password_is_read_from_parameter_store_and_never_written_out():
    output = _run(["dev"]).stdout

    # Only the password step is checked. The settings step uses --from-literal for bucket names,
    # which are not secret.
    secrets_step = _section(output, "create the database secrets")
    assert "/portfolio/dev/platform/airflow-db-password" in secrets_step
    assert "--with-decryption" in secrets_step
    assert "--from-literal" not in secrets_step
    assert "stringData" not in secrets_step


def test_the_backup_is_restored_after_airflow_is_installed_and_before_it_restarts():
    output = _run(["dev"]).stdout

    install = output.index("install airflow")
    restore = output.index("restore the database backup")
    restart = output.index("restart airflow")
    assert install < restore < restart
    assert "airflow_db_backup.py restore --bucket portfolio-dev-lake-123456789012" in output


def test_the_script_stops_at_the_first_failing_step(tmp_path):
    text = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text


def test_the_bucket_names_go_into_a_settings_object_that_holds_no_secret():
    output = _run(["dev"]).stdout

    settings_line = next(line for line in output.splitlines() if "configmap" in line)
    assert "platform-settings" in settings_line
    assert "PLATFORM_SITE_BUCKET=portfolio-dev-site-123456789012" in settings_line
    assert "PLATFORM_LAKE_BUCKET=portfolio-dev-lake-123456789012" in settings_line
    assert "PLATFORM_WAREHOUSE=s3://portfolio-dev-lake-123456789012/warehouse" in settings_line
    assert "password" not in settings_line.lower()


def test_airflow_is_told_its_environment_and_where_to_send_alerts():
    output = _run(["dev"]).stdout

    settings_line = next(line for line in output.splitlines() if "configmap" in line)
    assert "PLATFORM_ENV=dev" in settings_line
    assert f"PLATFORM_ALERT_TOPIC_ARN={REQUIRED_SETTINGS['ALERT_TOPIC_ARN']}" in settings_line


def test_an_alert_topic_from_the_other_environment_is_refused():
    result = _run(["dev"], settings={**REQUIRED_SETTINGS, "ALERT_TOPIC_ARN": LIVE_TOPIC})

    assert result.returncode == 2
    assert "ALERT_TOPIC_ARN" in result.stderr
    assert "STEP" not in result.stdout


def test_the_settings_object_is_made_before_airflow_needs_it():
    output = _run(["dev"]).stdout

    assert output.index("create the platform settings") < output.index("install airflow")


def test_the_python_tools_are_installed_before_the_restore_needs_them():
    output = _run(["dev"]).stdout

    assert output.index("install the python tools") < output.index("restore the database backup")
    tools = _section(output, "install the python tools")
    assert "python3.11" in tools
    assert "requirements-host.txt" in tools


def test_the_watchdog_starts_last_as_a_service_that_restarts_if_it_stops():
    output = _run(["dev"]).stdout

    assert _steps(output)[-1].endswith("start the watchdog")
    watchdog = _section(output, "start the watchdog")
    assert "box-watchdog.service" in watchdog
    assert "systemctl enable --now box-watchdog" in watchdog
    assert "Restart=on-failure" in watchdog


def test_the_watchdog_service_knows_the_bucket_the_cluster_and_where_the_code_is():
    watchdog = _section(_run(["dev"]).stdout, "start the watchdog")

    assert "box_watchdog.py --bucket portfolio-dev-lake-123456789012" in watchdog
    assert "KUBECONFIG=/etc/rancher/k3s/k3s.yaml" in watchdog
    assert "pipelines/platform/publish" in watchdog
    assert "platform/box" in watchdog


def test_the_watchdog_can_email_me_when_it_stops_a_run():
    watchdog = _section(_run(["dev"]).stdout, "start the watchdog")

    assert "--env dev" in watchdog
    assert f"--alert-topic-arn {REQUIRED_SETTINGS['ALERT_TOPIC_ARN']}" in watchdog


def test_helm_and_kubectl_are_pointed_at_the_k3s_cluster():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml" in text
