"""Tests for ecr_registry_login.sh, which lets k3s pull images from the private ECR repository.

A stand-in for the aws command prints a fixed password, so the script runs for real and writes
its file into a temporary folder instead of /etc/rancher/k3s.
"""

import os
import subprocess
from pathlib import Path

import pytest
from test_install_script import BASH

SCRIPT = Path(__file__).resolve().parent.parent / "ecr_registry_login.sh"
REGISTRY = "123456789012.dkr.ecr.us-east-1.amazonaws.com"
PASSWORD = "not-a-real-ecr-password"

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not available here")


def _fake_aws(tmp_path: Path, exit_code: int = 0) -> Path:
    folder = tmp_path / "bin"
    folder.mkdir()
    aws = folder / "aws"
    aws.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" > "{(tmp_path / "aws-args").as_posix()}"\n'
        f"echo {PASSWORD}\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
        newline="\n",
    )
    aws.chmod(0o755)
    return folder


def _run(tmp_path: Path, *arguments: str, exit_code: int = 0):
    folder = _fake_aws(tmp_path, exit_code)
    environment = {
        **os.environ,
        "PATH": f"{folder}{os.pathsep}{os.environ['PATH']}",
        "REGISTRIES_PATH": str(tmp_path / "registries.yaml"),
    }
    return subprocess.run(
        [BASH, str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_it_writes_the_registry_password_where_k3s_reads_it(tmp_path):
    result = _run(tmp_path, REGISTRY)

    assert result.returncode == 0, result.stderr
    written = (tmp_path / "registries.yaml").read_text(encoding="utf-8")
    assert f'"{REGISTRY}":' in written
    assert "username: AWS" in written
    assert f"password: {PASSWORD}" in written


def test_it_asks_for_the_password_in_the_registry_region(tmp_path):
    _run(tmp_path, REGISTRY)

    arguments = (tmp_path / "aws-args").read_text(encoding="utf-8").split()
    assert arguments[:2] == ["ecr", "get-login-password"]
    assert arguments[arguments.index("--region") + 1] == "us-east-1"


def test_the_password_is_never_printed(tmp_path):
    result = _run(tmp_path, REGISTRY)

    assert PASSWORD not in result.stdout
    assert PASSWORD not in result.stderr


def test_a_failed_sign_in_keeps_the_old_file_and_fails(tmp_path):
    old = tmp_path / "registries.yaml"
    old.write_text("the previous file\n", encoding="utf-8")

    result = _run(tmp_path, REGISTRY, exit_code=1)

    assert result.returncode != 0
    assert old.read_text(encoding="utf-8") == "the previous file\n"


def test_a_registry_that_is_not_ecr_is_refused(tmp_path):
    result = _run(tmp_path, "registry.example.com")

    assert result.returncode == 2
    assert not (tmp_path / "registries.yaml").exists()
