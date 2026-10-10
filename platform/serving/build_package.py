"""Builds the zip file that the serving Lambda function runs.

The zip holds the app's Python files and its dependencies, built for arm64 and Python 3.12.
It is deterministic: the same inputs give the same bytes, so Terraform sees a change only
when the code or the dependencies really change.

Run it from the repo root:
    python platform/serving/build_package.py
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SERVING_DIR = Path(__file__).resolve().parent
BUILD_DIR = SERVING_DIR / "build"
ZIP_PATH = BUILD_DIR / "function.zip"

# A fixed timestamp in every zip entry keeps the file identical from one build to the next.
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_EXCLUDED_SOURCE_FILES = {"build_package.py"}


def serving_source_files(serving_dir: Path) -> list[Path]:
    """Return the runtime Python files in the serving folder, without tests or this script."""
    return sorted(
        path for path in serving_dir.glob("*.py") if path.name not in _EXCLUDED_SOURCE_FILES
    )


def build_zip(serving_dir: Path, dependencies_dir: Path, output_path: Path) -> None:
    """Write the zip with the source files and the dependencies at the top level."""
    entries: dict[str, Path] = {}
    for path in serving_source_files(serving_dir):
        entries[path.name] = path
    for path in dependencies_dir.rglob("*"):
        relative = path.relative_to(dependencies_dir)
        if path.is_file() and "__pycache__" not in relative.parts and path.suffix != ".pyc":
            entries[relative.as_posix()] = path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, entries[name].read_bytes())


def sha256_base64(path: Path) -> str:
    """Return the file's SHA-256 as base64, the format Terraform's source_code_hash uses."""
    return base64.b64encode(hashlib.sha256(path.read_bytes()).digest()).decode("ascii")


def install_dependencies(requirements: Path, target_dir: Path) -> None:
    """Download arm64 wheels for Python 3.12 into ``target_dir``. This needs the internet.

    Lambda's Python 3.12 runtime is Amazon Linux 2023 (glibc 2.34), so wheels tagged
    manylinux_2_28 or the older manylinux2014 both run there.
    """
    shutil.rmtree(target_dir, ignore_errors=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--requirement",
            str(requirements),
            "--target",
            str(target_dir),
            "--platform",
            "manylinux_2_28_aarch64",
            "--platform",
            "manylinux2014_aarch64",
            "--python-version",
            "3.12",
            "--implementation",
            "cp",
            "--only-binary=:all:",
            "--no-compile",
        ],
        check=True,
    )


def main() -> None:
    """Install the dependencies, build the zip, and print its path and checksum."""
    dependencies_dir = BUILD_DIR / "dependencies"
    install_dependencies(SERVING_DIR / "requirements.txt", dependencies_dir)
    build_zip(SERVING_DIR, dependencies_dir, ZIP_PATH)
    print(f"Built {ZIP_PATH}")
    print(f"lambda_zip_sha256 = {sha256_base64(ZIP_PATH)}")


if __name__ == "__main__":
    main()
