"""Rules for the GitHub workflows that reach AWS (design doc section 7.1).

The workflows cannot run on my machine, so these tests read the YAML and check the rules that
keep AWS safe: who can use which role, what waits for approval, and the order of the steps.
actionlint, in CI, checks that the files are valid workflows.
"""

from pathlib import Path

import pytest
import yaml

GITHUB = Path(__file__).resolve().parent.parent
WORKFLOWS = GITHUB / "workflows"
ACTIONS = GITHUB / "actions"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # YAML 1.1 reads the key `on` as True.
    return workflow.get("on", workflow.get(True))


def _runs(job_or_action: dict) -> str:
    return "\n".join(step.get("run", "") for step in job_or_action.get("steps", []))


def _uses(job_or_action: dict) -> list[str]:
    return [step["uses"] for step in job_or_action.get("steps", []) if "uses" in step]


@pytest.fixture(scope="module")
def terraform():
    return _load(WORKFLOWS / "terraform.yml")


@pytest.fixture(scope="module")
def terraform_apply():
    return _load(WORKFLOWS / "terraform-apply.yml")


@pytest.fixture(scope="module")
def deploy():
    return _load(WORKFLOWS / "deploy.yml")


@pytest.fixture(scope="module")
def deploy_environment():
    return _load(WORKFLOWS / "deploy-environment.yml")


@pytest.fixture(scope="module")
def terraform_init():
    return _load(ACTIONS / "terraform-init" / "action.yml")


# --- Every workflow -------------------------------------------------------------------------


def _all_workflows():
    return sorted(WORKFLOWS.glob("*.yml"))


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_every_workflow_starts_with_read_only_permissions(path):
    assert _load(path).get("permissions") == {"contents": "read"}


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_no_workflow_runs_pull_requests_with_the_repository_secrets(path):
    assert "pull_request_target" not in _triggers(_load(path))


@pytest.mark.parametrize(
    "path", [*_all_workflows(), *sorted(ACTIONS.glob("*/action.yml"))], ids=lambda p: p.name
)
def test_every_outside_action_is_pinned_to_a_version(path):
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "uses:" in line and "./" not in line:
            reference = line.split("uses:")[1].strip()
            assert "@" in reference, line
            assert reference.split("@")[1] not in {"main", "master", "latest"}, line


# --- Terraform: plan on pull requests, apply after approval ---------------------------------


def test_terraform_runs_on_pull_requests_and_on_merges_to_main(terraform):
    triggers = _triggers(terraform)
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["push"]["branches"] == ["main"]


def test_the_plan_runs_for_both_environments_on_pull_requests_only(terraform):
    plan = terraform["jobs"]["plan"]
    assert "github.event_name == 'pull_request'" in plan["if"]
    assert {entry["env"] for entry in plan["strategy"]["matrix"]["include"]} == {"dev", "live"}


def test_the_plan_skips_pull_requests_from_forks(terraform):
    assert "head.repo.full_name == github.repository" in terraform["jobs"]["plan"]["if"]


def test_the_plan_uses_the_plan_role_and_writes_nothing(terraform):
    plan = terraform["jobs"]["plan"]
    text = yaml.safe_dump(plan)
    assert "TF_PLAN_ROLE_ARN_" in text
    assert "TF_APPLY_ROLE_ARN" not in text
    assert "-lock=false" in _runs(plan)
    assert "terraform apply" not in _runs(plan)
    assert "environment" not in plan


def test_dev_is_applied_first_and_live_only_after_dev(terraform):
    jobs = terraform["jobs"]
    assert jobs["apply-dev"]["with"]["env"] == "dev"
    assert jobs["apply-live"]["with"]["env"] == "live"
    assert jobs["apply-live"]["needs"] == "apply-dev"
    for name in ("apply-dev", "apply-live"):
        assert jobs[name]["uses"] == "./.github/workflows/terraform-apply.yml"
        assert "github.event_name == 'push'" in jobs[name]["if"]


def test_the_apply_waits_for_the_github_environment_and_uses_its_role(terraform_apply):
    job = terraform_apply["jobs"]["apply"]
    assert job["environment"] == "${{ inputs.env }}"
    assert "vars.TF_APPLY_ROLE_ARN" in yaml.safe_dump(job)
    assert job["permissions"] == {"contents": "read", "id-token": "write"}


def test_the_apply_runs_exactly_the_plan_it_made(terraform_apply):
    runs = _runs(terraform_apply["jobs"]["apply"])
    assert "terraform plan" in runs and "-out=tfplan" in runs
    assert "terraform apply" in runs and "tfplan" in runs.split("terraform apply")[1]
    assert runs.index("terraform plan") < runs.index("terraform apply")


def test_two_applies_never_run_at_the_same_time(terraform):
    concurrency = terraform["concurrency"]
    assert concurrency["cancel-in-progress"] is False
    assert "apply" in concurrency["group"]


@pytest.mark.parametrize("job", ["plan", "apply-dev", "apply-live"])
def test_terraform_jobs_skip_until_aws_is_set_up(terraform, job):
    assert "vars.TF_STATE_BUCKET != ''" in terraform["jobs"][job]["if"]


def test_alert_addresses_come_from_secrets_not_variables(terraform, terraform_apply):
    for document in (terraform, terraform_apply):
        text = yaml.safe_dump(document)
        assert "secrets[format('ALERT_EMAILS_" in text
        assert "vars[format('ALERT_EMAILS_" not in text


def test_init_reads_the_state_for_the_right_environment(terraform_init):
    runs = _runs(terraform_init["runs"])
    assert "key=${ENV}/terraform.tfstate" in runs
    assert "terraform init" in runs
    assert "build_package.py" in runs


# --- Deploy: dev, then live -----------------------------------------------------------------


def test_deploy_runs_only_on_merges_to_main(deploy):
    assert set(_triggers(deploy)) == {"push"}
    assert _triggers(deploy)["push"]["branches"] == ["main"]


def test_the_image_is_built_on_arm_and_scanned_before_any_deploy(deploy):
    image = deploy["jobs"]["image"]
    assert image["runs-on"] == "ubuntu-24.04-arm"
    names = [step.get("name", "") for step in image["steps"]]
    scan = next(i for i, name in enumerate(names) if "Scan" in name)
    upload = next(
        i for i, step in enumerate(image["steps"]) if "upload-artifact" in step.get("uses", "")
    )
    assert scan < upload
    assert "vars.TF_STATE_BUCKET != ''" in image["if"]


def test_dev_is_deployed_first_and_live_only_after_dev(deploy):
    jobs = deploy["jobs"]
    assert jobs["dev"]["needs"] == "image"
    assert jobs["live"]["needs"] == "dev"
    assert jobs["dev"]["with"]["env"] == "dev"
    assert jobs["live"]["with"]["env"] == "live"


def test_the_deploy_waits_for_the_github_environment_and_uses_its_role(deploy_environment):
    job = deploy_environment["jobs"]["deploy"]
    assert job["environment"] == "${{ inputs.env }}"
    assert "vars.DEPLOY_ROLE_ARN" in yaml.safe_dump(job)


def test_the_site_upload_leaves_the_box_files_alone(deploy_environment):
    runs = _runs(deploy_environment["jobs"]["deploy"])
    sync = next(line for line in runs.splitlines() if "aws s3 sync" in line)
    assert "--delete" in sync
    assert '--exclude "published/*"' in sync
    assert '--exclude "status.json"' in sync


def test_the_image_is_tagged_with_the_commit(deploy_environment):
    runs = _runs(deploy_environment["jobs"]["deploy"])
    assert "docker push" in runs
    assert "${GITHUB_SHA}" in runs
