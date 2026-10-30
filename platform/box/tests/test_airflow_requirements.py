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
