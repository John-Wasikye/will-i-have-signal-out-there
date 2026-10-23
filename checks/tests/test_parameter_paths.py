"""Tests for the Parameter Store path check (design doc section 7.9, OQ-P10).

Every path a project uses is listed in checks/parameter_paths.yaml. The check makes sure each
listed path follows /portfolio/<env>/<project>/<name>, that the code uses no path missing from
the list, that the list holds no path nothing uses, and, with AWS access, that each listed
parameter exists.
"""

from pathlib import Path

import pytest
from parameter_paths import (
    ENV_PLACEHOLDER,
    check_repository,
    find_paths,
    main,
    missing_in_aws,
    normalise,
    rule_problems,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- The naming rule ------------------------------------------------------------------------


def test_a_path_that_follows_the_rule_has_no_problem():
    assert rule_problems("/portfolio/<env>/platform/airflow-db-password") == []


@pytest.mark.parametrize(
    "path",
    [
        "/portfolio/<env>/platform",  # no name
        "/portfolio/<env>/platform/db/password",  # one segment too many
        "/portfolio/<env>/Platform/password",  # capital letter
        "/portfolio/<env>/platform/pass word",  # space
        "/portfolio/<env>//password",  # empty segment
        "/portfolio/dev/platform/password",  # a real environment instead of <env>
        "/other/<env>/platform/password",  # wrong root
    ],
)
def test_a_path_that_breaks_the_rule_is_reported(path):
    assert rule_problems(path) != []


# --- Reading paths out of the code ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "/portfolio/dev/airflow/connections",
        "/portfolio/live/airflow/connections",
        "/portfolio/${environment}/airflow/connections",
        "/portfolio/{env}/airflow/connections",
        "/portfolio/<env>/airflow/connections",
    ],
)
def test_every_way_of_writing_the_environment_becomes_the_placeholder(raw):
    assert normalise(raw) == f"/portfolio/{ENV_PLACEHOLDER}/airflow/connections"


def test_an_unknown_environment_is_kept_so_the_rule_reports_it():
    assert normalise("/portfolio/staging/airflow/connections") == (
        "/portfolio/staging/airflow/connections"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "/portfolio/${var.env}",  # the root of one environment, which IAM grants
        "/portfolio/${var.env}/*",
        "/portfolio/<env>/",  # the same root, written with a trailing slash
        "/portfolio/<env>/<project>/<name>",  # the rule itself, written in a comment
    ],
)
def test_grants_and_the_written_rule_are_not_paths_in_use(raw):
    assert normalise(raw) is None


def test_paths_are_found_in_code_but_not_in_docs_or_tests(tmp_path):
    (tmp_path / "install.sh").write_text(
        'name="/portfolio/${environment}/platform/db-password"\n', encoding="utf-8"
    )
    (tmp_path / "notes.md").write_text("/portfolio/dev/platform/old-name\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        'BAD = "/portfolio/dev/Bad/Name"\n', encoding="utf-8"
    )

    found = find_paths(tmp_path)

    assert found == {"/portfolio/<env>/platform/db-password": {"install.sh"}}


# --- The whole check ------------------------------------------------------------------------


def _write_repo(root: Path, code: str, listed: str) -> None:
    (root / "checks").mkdir()
    (root / "checks" / "parameter_paths.yaml").write_text(listed, encoding="utf-8")
    (root / "run.sh").write_text(code, encoding="utf-8")


def test_a_path_used_in_code_but_not_listed_is_reported_with_its_file(tmp_path):
    _write_repo(tmp_path, 'x="/portfolio/dev/platform/token"\n', "parameters: []\nprefixes: []\n")

    problems = check_repository(tmp_path)

    assert any("/portfolio/<env>/platform/token" in p and "run.sh" in p for p in problems)


def test_a_listed_path_that_nothing_uses_is_reported(tmp_path):
    listed = (
        "parameters:\n"
        "  - path: /portfolio/<env>/platform/old-token\n"
        "    used_by: run.sh\n"
        "    description: Not used any more.\n"
        "prefixes: []\n"
    )
    _write_repo(tmp_path, "echo nothing\n", listed)

    problems = check_repository(tmp_path)

    assert any("old-token" in p and "not used" in p for p in problems)


def test_a_listed_path_that_breaks_the_rule_is_reported(tmp_path):
    listed = (
        "parameters:\n"
        "  - path: /portfolio/<env>/Platform/Token\n"
        "    used_by: run.sh\n"
        "    description: Capital letters.\n"
        "prefixes: []\n"
    )
    _write_repo(tmp_path, 'x="/portfolio/dev/Platform/Token"\n', listed)

    assert any("Platform/Token" in p for p in check_repository(tmp_path))


def test_this_repository_follows_the_rules():
    assert check_repository(REPO_ROOT) == []


# --- Whether the parameters exist in AWS ----------------------------------------------------


class FakeSsm:
    def __init__(self, existing: set[str]):
        self.existing = existing
        self.calls = []

    def describe_parameters(self, ParameterFilters):  # noqa: N803 (boto3's argument name)
        self.calls.append(ParameterFilters)
        name = ParameterFilters[0]["Values"][0]
        found = [{"Name": name}] if name in self.existing else []
        return {"Parameters": found}


def test_a_listed_parameter_missing_in_aws_is_reported_for_that_environment():
    ssm = FakeSsm(existing=set())

    missing = missing_in_aws(ssm, ["/portfolio/<env>/platform/airflow-db-password"], "live")

    assert missing == ["/portfolio/live/platform/airflow-db-password"]


def test_a_parameter_that_exists_is_not_reported_and_only_names_are_asked_for():
    ssm = FakeSsm(existing={"/portfolio/dev/platform/airflow-db-password"})

    assert missing_in_aws(ssm, ["/portfolio/<env>/platform/airflow-db-password"], "dev") == []
    assert ssm.calls[0] == [
        {
            "Key": "Name",
            "Option": "Equals",
            "Values": ["/portfolio/dev/platform/airflow-db-password"],
        }
    ]


def test_the_aws_check_refuses_an_unknown_environment():
    with pytest.raises(ValueError, match="dev or live"):
        missing_in_aws(FakeSsm(set()), [], "staging")


# --- The command line -----------------------------------------------------------------------


def test_the_command_passes_on_this_repository(capsys):
    assert main(["--root", str(REPO_ROOT)]) == 0


def test_the_command_fails_and_prints_each_problem(tmp_path, capsys):
    _write_repo(tmp_path, 'x="/portfolio/dev/platform/token"\n', "parameters: []\nprefixes: []\n")

    assert main(["--root", str(tmp_path)]) == 1
    assert "/portfolio/<env>/platform/token" in capsys.readouterr().out
