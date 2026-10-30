"""The packages added to the Airflow image are pinned to exact versions (CONTRIBUTING.md)."""

from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements-airflow.txt"


def test_every_added_package_names_an_exact_version():
    lines = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()]
    packages = [line for line in lines if line and not line.startswith("#")]
    assert packages
    for package in packages:
        name, _, version = package.partition("==")
        assert name and version, package
