"""Tests for the Airflow chart settings, checked on the manifests Helm really renders.

I render the official chart with my settings file and look at the result, so the tests
check what Kubernetes would receive, not just what I wrote. They use Helm when it is
installed, or Docker when it is not, and skip when neither is available.
"""

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BOX_DIR = Path(__file__).resolve().parent.parent
CHART_VERSION = "1.22.0"
LONG_TIMEOUT_SECONDS = 300


def _helm_prefix() -> list[str] | None:
    """Return the command that starts Helm, or None when Helm cannot be run here."""
    if shutil.which("helm"):
        return ["helm"]
    if shutil.which("docker"):
        daemon = subprocess.run(["docker", "info"], capture_output=True, check=False)
        if daemon.returncode == 0:
            return [
                "docker",
                "run",
                "--rm",
                "--volume",
                f"{BOX_DIR}:/work",
                "alpine/helm:latest",
            ]
    return None


def _render(values_names: list[str]) -> list[dict]:
    """Render the chart with the named settings files, in order, and return the objects."""
    prefix = _helm_prefix()
    if prefix is None:
        pytest.skip("neither helm nor a running Docker is available here")

    in_docker = prefix[0] == "docker"
    values_args: list[str] = []
    for name in values_names:
        path = f"/work/{name}" if in_docker else str(BOX_DIR / name)
        values_args += ["--values", path]

    command = [
        *prefix,
        "template",
        "airflow",
        "airflow",
        "--repo",
        "https://airflow.apache.org",
        "--version",
        CHART_VERSION,
        "--namespace",
        "airflow",
        *values_args,
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=LONG_TIMEOUT_SECONDS
    )
    assert result.returncode == 0, result.stderr
    return [document for document in yaml.safe_load_all(result.stdout) if document]


@pytest.fixture(scope="module")
def dev_objects() -> list[dict]:
    return _render(["airflow-values.yaml"])


@pytest.fixture(scope="module")
def live_objects() -> list[dict]:
    return _render(["airflow-values.yaml", "airflow-values-live.yaml"])


def _airflow_cfg(objects: list[dict]) -> configparser.ConfigParser:
    config_map = next(
        item
        for item in objects
        if item["kind"] == "ConfigMap" and "airflow.cfg" in item.get("data", {})
    )
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(config_map["data"]["airflow.cfg"])
    return parser


def _pod_templates(objects: list[dict]) -> list[dict]:
    kinds = {"Deployment", "StatefulSet", "Job"}
    return [item["spec"]["template"] for item in objects if item["kind"] in kinds]


def test_airflow_runs_everything_in_one_process_group_with_the_local_executor(dev_objects):
    assert _airflow_cfg(dev_objects)["core"]["executor"] == "LocalExecutor"


def test_no_celery_parts_are_installed(dev_objects):
    names = " ".join(item["metadata"]["name"] for item in dev_objects)
    for unwanted in ("redis", "worker", "flower", "statsd", "pgbouncer"):
        assert unwanted not in names, f"{unwanted} should not be installed"


def test_the_dags_come_from_the_pipeline_folder_in_the_image(dev_objects):
    assert _airflow_cfg(dev_objects)["core"]["dags_folder"] == (
        "/opt/airflow/pipelines/platform/dags"
    )


def test_connection_keys_are_read_from_parameter_store(dev_objects):
    secrets = _airflow_cfg(dev_objects)["secrets"]
    assert secrets["backend"] == (
        "airflow.providers.amazon.aws.secrets.systems_manager.SystemsManagerParameterStoreBackend"
    )
    assert "/portfolio/dev/airflow/connections" in secrets["backend_kwargs"]


def test_the_live_install_reads_the_live_parameter_path(live_objects):
    secrets = _airflow_cfg(live_objects)["secrets"]
    assert "/portfolio/live/airflow/connections" in secrets["backend_kwargs"]
    assert "/portfolio/dev" not in secrets["backend_kwargs"]


def test_no_default_admin_user_with_a_known_password_is_created(dev_objects):
    job_names = [item["metadata"]["name"] for item in dev_objects if item["kind"] == "Job"]
    assert not any("create-user" in name for name in job_names)


def test_every_container_has_cpu_and_memory_limits(dev_objects):
    missing = []
    for template in _pod_templates(dev_objects):
        for container in template["spec"].get("containers", []):
            limits = container.get("resources", {}).get("limits", {})
            if "cpu" not in limits or "memory" not in limits:
                missing.append(container["name"])
    assert missing == [], f"containers without limits: {missing}"


def test_nothing_is_exposed_outside_the_box(dev_objects):
    kinds = {item["kind"] for item in dev_objects}
    assert "Ingress" not in kinds
    for item in dev_objects:
        if item["kind"] == "Service":
            assert item["spec"].get("type", "ClusterIP") == "ClusterIP"


def test_the_pods_use_my_airflow_image(dev_objects):
    images = {
        container["image"]
        for template in _pod_templates(dev_objects)
        for container in template["spec"].get("containers", [])
        if container["name"] in {"scheduler", "api-server", "dag-processor"}
    }
    assert images == {"portfolio-airflow:3.3.2"}


def test_the_database_password_comes_from_secrets_made_outside_the_chart(dev_objects):
    """The install script makes these two secrets from Parameter Store, so no default is used."""
    import base64

    for item in dev_objects:
        if item["kind"] != "Secret":
            continue
        values = [base64.b64decode(v).decode() for v in item.get("data", {}).values()]
        values += list(item.get("stringData", {}).values())
        assert "postgres" not in values, f"{item['metadata']['name']} holds the default password"
        assert "admin" not in values, f"{item['metadata']['name']} holds the default password"

    pod_text = yaml.safe_dump([_pod_templates(dev_objects)])
    assert "airflow-postgres" in pod_text
    assert "airflow-metadata-connection" in yaml.safe_dump(dev_objects)


def _scheduler_container(objects: list[dict]) -> dict:
    scheduler = next(
        item
        for item in objects
        if item["kind"] == "StatefulSet" and item["metadata"]["name"] == "airflow-scheduler"
    )
    containers = scheduler["spec"]["template"]["spec"]["containers"]
    return next(container for container in containers if container["name"] == "scheduler")


def test_the_pipeline_folders_are_set_inside_the_airflow_home(dev_objects):
    environment = {e["name"]: e.get("value") for e in _scheduler_container(dev_objects)["env"]}

    assert environment["PLATFORM_PUBLISHED_DIR"] == "/opt/airflow/data/published"
    assert environment["PLATFORM_METRICS_DIR"] == "/opt/airflow/data/metrics"
    assert environment["PLATFORM_INCIDENTS_DIR"] == "/opt/airflow/data/incidents"
    assert environment["PLATFORM_USE_GLUE"] == "1"


def test_the_bucket_names_come_from_a_settings_object_made_at_install(dev_objects):
    env_from = _scheduler_container(dev_objects).get("envFrom", [])

    assert {"configMapRef": {"name": "platform-settings"}} in env_from


def test_the_database_is_migrated_by_a_plain_job_that_helm_waits_for(dev_objects):
    # install.sh runs helm with --wait. The chart's migration job is a post-install hook by
    # default, and Helm runs post-install hooks only after --wait is satisfied, while the
    # scheduler, the API server and the DAG processor wait for the migration before they start.
    # On the first real box the install timed out with the job never created. As a plain
    # resource, the job runs with everything else.
    jobs = [item for item in dev_objects if item["kind"] == "Job"]
    migration = next(job for job in jobs if "run-airflow-migrations" in job["metadata"]["name"])
    annotations = migration["metadata"].get("annotations") or {}
    assert "helm.sh/hook" not in annotations
