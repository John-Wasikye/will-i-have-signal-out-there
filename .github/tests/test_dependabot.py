"""Rules for Dependabot (.github/dependabot.yml).

Dependabot may only propose updates that should pass CI on their own: minor and patch
versions. Major versions, Terraform providers and the versions tied to Airflow are planned
work on their own branch, where the Terraform plan runs and I can read it before I merge.
"""

from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "dependabot.yml"
MAJOR = "version-update:semver-major"


def _updates() -> list[dict]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["updates"]


def _ignored(update: dict, name: str) -> set[str]:
    types: set[str] = set()
    for rule in update.get("ignore", []):
        if rule["dependency-name"] == name:
            # A rule without update-types ignores every update of that dependency.
            types |= set(rule.get("update-types", ["all"]))
    return types


def _name(update: dict) -> str:
    return f"{update['package-ecosystem']}{update['directory']}"


def _update(ecosystem: str, directory: str) -> dict:
    matches = [
        u
        for u in _updates()
        if u["package-ecosystem"] == ecosystem and u.get("directory") == directory
    ]
    assert len(matches) == 1
    return matches[0]


def test_terraform_providers_are_updated_by_hand_where_the_plan_runs():
    assert "terraform" not in {u["package-ecosystem"] for u in _updates()}


def test_the_airflow_base_image_is_updated_by_hand_with_its_constraint_file():
    assert "docker" not in {u["package-ecosystem"] for u in _updates()}


@pytest.mark.parametrize("update", _updates(), ids=_name)
def test_no_major_version_is_proposed(update):
    assert MAJOR in _ignored(update, "*")


@pytest.mark.parametrize("update", _updates(), ids=_name)
def test_groups_hold_only_minor_and_patch_updates(update):
    for group in update.get("groups", {}).values():
        assert set(group["update-types"]) == {"minor", "patch"}


def test_spark_stays_on_the_line_the_iceberg_runtime_is_built_for():
    box = _update("pip", "/platform/box")
    assert {"version-update:semver-minor", MAJOR} <= _ignored(box, "pyspark")


def test_the_box_pyarrow_stays_on_the_version_airflow_pins():
    assert _ignored(_update("pip", "/platform/box"), "pyarrow") == {"all"}


def test_the_root_python_ranges_are_raised_by_hand():
    # The root file holds ranges, and Dependabot raises a range's ceiling across a major
    # version even with majors ignored. CI already installs the newest version in each range.
    assert ("pip", "/") not in {(u["package-ecosystem"], u["directory"]) for u in _updates()}


def test_the_api_packages_are_updated_by_hand_where_the_plan_runs():
    # A change under platform/serving starts the Terraform plan, which a Dependabot pull
    # request cannot sign in for.
    assert "/platform/serving" not in {u["directory"] for u in _updates()}


def test_action_updates_leave_the_terraform_workflows_alone():
    # A change to these files starts the Terraform plan too.
    actions = _update("github-actions", "/")
    assert {".github/workflows/terraform*.yml", ".github/actions/terraform-init/**"} <= set(
        actions.get("exclude-paths", [])
    )
