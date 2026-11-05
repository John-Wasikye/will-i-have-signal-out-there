"""The box's Python packages: pinned to exact versions (CONTRIBUTING.md), and pyarrow is one
version everywhere, free of the known pyarrow flaw (CVE-2026-25087, fixed in 23.0.1)."""

import re
from pathlib import Path

BOX = Path(__file__).resolve().parent.parent
REQUIREMENTS = BOX / "requirements-airflow.txt"
HOST_REQUIREMENTS = BOX / "requirements-host.txt"
PYPROJECT = BOX.parent.parent / "pyproject.toml"
FIXED = (23, 0, 1)


def test_every_added_package_names_an_exact_version():
    lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()]
    packages = [line for line in lines if line and not line.startswith("#")]
    assert packages
    for package in packages:
        name, _, version = package.partition("==")
        assert name and version, package


def _pin(path: Path, name: str) -> str:
    match = re.search(rf"^{name}==(\S+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{name} is not pinned in {path.name}"
    return match.group(1)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_the_host_scripts_use_the_same_pyarrow_as_the_image():
    assert _pin(HOST_REQUIREMENTS, "pyarrow") == _pin(REQUIREMENTS, "pyarrow")


def test_the_box_pyarrow_has_the_fix():
    assert _version(_pin(REQUIREMENTS, "pyarrow")) >= FIXED


def test_the_laptop_and_ci_range_allows_no_pyarrow_without_the_fix():
    match = re.search(r'"pyarrow>=([\d.]+),', PYPROJECT.read_text(encoding="utf-8"))
    assert match
    assert _version(match.group(1)) >= FIXED


CI_WORKFLOW = BOX.parent.parent / ".github" / "workflows" / "ci.yml"
SMOKE_TEST = BOX / "smoke_test_airflow_image.sh"
CI_AIRFLOW_INSTALL = r'"apache-airflow==\$\{AIRFLOW_VERSION\}"([^\n]*)'


def test_the_satellite_window_engine_gets_sgp4_everywhere_it_runs():
    """C5 imports sgp4 in the image, on the laptop and in CI's DAG test job.

    That CI job installs its own package list, so a package missing there fails only in CI.
    """
    pinned = _pin(REQUIREMENTS, "sgp4")
    match = re.search(r'"sgp4>=([\d.]+),<([\d.]+)"', PYPROJECT.read_text(encoding="utf-8"))
    assert match, "sgp4 has no range in pyproject.toml"
    assert _version(match.group(1)) <= _version(pinned) < _version(match.group(2))

    install = re.search(CI_AIRFLOW_INSTALL, CI_WORKFLOW.read_text(encoding="utf-8"))
    packages = [word.partition("==")[0] for word in install.group(1).split()] if install else []
    assert "sgp4" in packages, "CI's DAG test job does not install sgp4"

    smoke = SMOKE_TEST.read_text(encoding="utf-8")
    assert re.search(r"import [^\n]*\bsgp4\b", smoke), "the image smoke test does not import sgp4"


DBT_REQUIREMENTS = BOX / "requirements-dbt.txt"
DOCKERFILE = BOX / "Dockerfile.airflow"
SERVING_REQUIREMENTS = BOX.parent / "serving" / "requirements.txt"


def test_dbt_stays_out_of_airflows_python_environment():
    """Airflow's constraint file pins pathspec 1.1.1 and dbt-core needs it below 0.13."""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert "dbt" not in re.sub(r"#.*", "", text)


def test_every_dbt_package_is_pinned_so_it_installs_without_a_resolver():
    lines = [
        line
        for line in DBT_REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert all(re.fullmatch(r"[a-z0-9-]+==[^\s=]+", line) for line in lines), lines
    assert {"dbt-core==1.11.16", "dbt-duckdb==1.11.1"} <= set(lines)


def test_dbt_and_the_api_use_the_same_duckdb():
    assert _pin(DBT_REQUIREMENTS, "duckdb") == _pin(SERVING_REQUIREMENTS, "duckdb")


def test_the_image_builds_dbt_its_own_environment_and_says_where_it_is():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "requirements-dbt.txt" in text
    assert "--no-deps" in text
    assert "ENV SIGNAL_DBT_BIN=" in text
    assert "ENV SIGNAL_DBT_PROJECT_DIR=" in text


def test_the_image_smoke_test_and_ci_run_dbt():
    assert "SIGNAL_DBT_BIN" in SMOKE_TEST.read_text(encoding="utf-8")
    assert "requirements-dbt.txt" in CI_WORKFLOW.read_text(encoding="utf-8")


def test_the_fcc_coverage_loader_gets_h3_everywhere_it_runs():
    """C6 imports h3 in the image, on the laptop and in CI's DAG test job."""
    pinned = _pin(REQUIREMENTS, "h3")
    match = re.search(r'"h3>=([\d.]+),<([\d.]+)"', PYPROJECT.read_text(encoding="utf-8"))
    assert match, "h3 has no range in pyproject.toml"
    assert _version(match.group(1)) <= _version(pinned) < _version(match.group(2))

    install = re.search(CI_AIRFLOW_INSTALL, CI_WORKFLOW.read_text(encoding="utf-8"))
    packages = [word.partition("==")[0] for word in install.group(1).split()] if install else []
    assert "h3" in packages, "CI's DAG test job does not install h3"

    smoke = SMOKE_TEST.read_text(encoding="utf-8")
    assert re.search(r"import [^\n]*\bh3\b", smoke), "the image smoke test does not import h3"
