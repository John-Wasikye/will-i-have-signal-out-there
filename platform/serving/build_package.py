"""Builds the zip file that the serving Lambda function runs.

The zip holds the app's Python files and its dependencies, built for arm64 and Python 3.12.
It is deterministic: the same inputs give the same bytes, on any machine and on any day, so
Terraform sees a change only when the code or the dependencies really change. Every package
comes from requirements-lock.txt with its version and hash, and the files that pip writes
differently on Windows and Linux stay out of the zip.

After changing requirements.txt, refresh the lock with the command at the top of
requirements-lock.txt.

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
REQUIREMENTS_PATH = SERVING_DIR / "requirements.txt"
LOCK_PATH = SERVING_DIR / "requirements-lock.txt"

# A fixed timestamp in every zip entry keeps the file identical from one build to the next.
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_EXCLUDED_SOURCE_FILES = {"build_package.py"}


def _belongs_in_the_zip(relative: Path) -> bool:
    """Return True for a dependency file that belongs in the zip.

    Compiled caches stay out, and so does what pip writes per machine: console scripts in bin/,
    such as bin/fastapi.exe on Windows, and the RECORD file that lists them. Lambda needs
    neither. METADATA stays, because packages read their own version from it.
    """
    if "__pycache__" in relative.parts or relative.suffix == ".pyc":
        return False
    if relative.parts[0] == "bin":
        return False
    return not (relative.name == "RECORD" and relative.parent.name.endswith(".dist-info"))


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
        if path.is_file() and _belongs_in_the_zip(relative):
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


def install_dependencies(lock: Path, target_dir: Path) -> None:
    """Download arm64 wheels for Python 3.12 into ``target_dir``. This needs the internet.

    Only the locked packages are installed, each checked against its hash, so a new release
    of a package I did not choose cannot slip in. Lambda's Python 3.12 runtime is Amazon Linux
    2023 (glibc 2.34), so wheels tagged manylinux_2_28 or the older manylinux2014 both run there.
    """
    shutil.rmtree(target_dir, ignore_errors=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--requirement",
            str(lock),
            "--no-deps",
            "--require-hashes",
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
    install_dependencies(LOCK_PATH, dependencies_dir)
    build_zip(SERVING_DIR, dependencies_dir, ZIP_PATH)
    print(f"Built {ZIP_PATH}")
    print(f"lambda_zip_sha256 = {sha256_base64(ZIP_PATH)}")


if __name__ == "__main__":
    main()
