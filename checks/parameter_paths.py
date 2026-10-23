"""Checks the Parameter Store paths the projects use (design doc section 7.9, OQ-P10).

Every path is listed in checks/parameter_paths.yaml, written with <env> for the environment.
The check fails when:
- a listed path does not follow /portfolio/<env>/<project>/<name>
- the code uses a path that is not listed
- a listed path is used nowhere
- with --check-aws: a listed parameter does not exist in that environment

The AWS check asks only for parameter names, never their values.

Run it from the repo root:
    python checks/parameter_paths.py
    python checks/parameter_paths.py --check-aws --env dev
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml

ENV_PLACEHOLDER = "<env>"
ENVIRONMENTS = ("dev", "live")
LIST_FILE = Path("checks") / "parameter_paths.yaml"

_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Characters that can appear in a path written in code, including ${var} and {var} forms.
_PATH_IN_CODE = re.compile(r"/portfolio/[A-Za-z0-9_.${}<>*/-]*")
# The environment segment written as a real name, a shell or Terraform variable, or a
# Python format field.
_ENV_FORMS = re.compile(r"^(dev|live|<env>|\$\{[^}]*\}|\{[^}]*\})$")

_SCANNED_SUFFIXES = {".py", ".sh", ".yaml", ".yml", ".tf", ".json", ".ts", ".tsx", ".toml"}
_SKIPPED_FOLDERS = {".git", ".venv", "node_modules", ".terraform", "docs", "tests", "dist"}


def rule_problems(path: str) -> list[str]:
    """Return what is wrong with a listed path, or an empty list when it follows the rule."""
    segments = path.split("/")
    if len(segments) != 5 or segments[0] != "" or segments[1] != "portfolio":
        return [f"{path}: must look like /portfolio/{ENV_PLACEHOLDER}/<project>/<name>"]
    if segments[2] != ENV_PLACEHOLDER:
        return [f"{path}: the environment must be written as {ENV_PLACEHOLDER}"]
    return [
        f"{path}: '{segment}' must be lowercase letters, digits, '-' or '_'"
        for segment in segments[3:]
        if not _SEGMENT.match(segment)
    ]


def normalise(raw: str) -> str | None:
    """Return a path from the code with its environment as <env>.

    Return None for what is not a path in use: the root of an environment, which IAM grants,
    and the rule itself written out with <project> or <name>.
    """
    segments = raw.rstrip("./").split("/")
    if len(segments) < 3:
        return None
    if _ENV_FORMS.match(segments[2]):
        segments[2] = ENV_PLACEHOLDER
    rest = segments[3:]
    if not rest or rest == ["*"] or any(segment.startswith("<") for segment in rest):
        return None
    return "/".join(segments)


def _scanned_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _SKIPPED_FOLDERS for part in relative.parts):
            continue
        if path.is_file() and path.suffix in _SCANNED_SUFFIXES and relative != LIST_FILE:
            yield path


def find_paths(root: Path) -> dict[str, set[str]]:
    """Return each path the code uses, with the files that use it. Docs and tests are skipped."""
    found: dict[str, set[str]] = {}
    for path in _scanned_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw in _PATH_IN_CODE.findall(text):
            normalised = normalise(raw)
            if normalised is not None:
                found.setdefault(normalised, set()).add(path.relative_to(root).as_posix())
    return found


def load_list(root: Path) -> tuple[list[str], list[str]]:
    """Return the listed parameters and prefixes."""
    document = yaml.safe_load((root / LIST_FILE).read_text(encoding="utf-8")) or {}
    parameters = [entry["path"] for entry in document.get("parameters") or []]
    prefixes = [entry["path"] for entry in document.get("prefixes") or []]
    return parameters, prefixes


def check_repository(root: Path) -> list[str]:
    """Return every problem with the listed paths and the paths in the code."""
    parameters, prefixes = load_list(root)
    listed = set(parameters) | set(prefixes)
    used = find_paths(root)

    problems = [problem for path in sorted(listed) for problem in rule_problems(path)]
    problems += [
        f"{path}: used in {', '.join(sorted(files))} but not listed in {LIST_FILE.as_posix()}"
        for path, files in sorted(used.items())
        if path not in listed
    ]
    problems += [
        f"{path}: listed in {LIST_FILE.as_posix()} but not used anywhere"
        for path in sorted(listed)
        if path not in used
    ]
    return problems


def missing_in_aws(client, parameters: Sequence[str], env: str) -> list[str]:  # noqa: ANN001
    """Return the listed parameters that do not exist in ``env``. ``client`` is a boto3 SSM client.

    DescribeParameters returns names and settings only, so no value is read.
    """
    if env not in ENVIRONMENTS:
        raise ValueError(f"env must be dev or live, got {env!r}")
    missing = []
    for path in parameters:
        name = path.replace(ENV_PLACEHOLDER, env)
        response = client.describe_parameters(
            ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
        )
        if not response["Parameters"]:
            missing.append(name)
    return missing


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check, print each problem, and return 1 if there is any."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="The repository root.")
    parser.add_argument("--check-aws", action="store_true", help="Also check AWS.")
    parser.add_argument("--env", choices=ENVIRONMENTS, help="The environment for --check-aws.")
    arguments = parser.parse_args(argv)
    if arguments.check_aws and arguments.env is None:
        parser.error("--check-aws needs --env")

    problems = check_repository(arguments.root)
    if arguments.check_aws:
        import boto3  # Only the AWS check needs boto3.

        parameters, _ = load_list(arguments.root)
        problems += [
            f"{name}: listed but does not exist in {arguments.env}"
            for name in missing_in_aws(boto3.client("ssm"), parameters, arguments.env)
        ]

    for problem in problems:
        print(problem)
    if not problems:
        print("Every Parameter Store path follows the rules.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
