# Session box

These are the files that run on the session box, the one computer that runs the nightly pipelines. The Terraform that creates the box is in `platform/terraform/modules/session_box`.

| File | What it does |
|---|---|
| `Dockerfile.airflow` | Builds the Airflow image: the official image, plus Java, PySpark and my pipeline code. |
| `requirements-airflow.txt` | The packages I add to that image. |
| `smoke_test_airflow_image.sh` | Checks the built image: Java is there, the imports work, the nightly DAG loads, and it does not run as root. |
| `airflow-values.yaml` | Settings for the official Airflow chart. Local executor, CPU and memory limits, connection keys from Parameter Store. |
| `airflow-values-live.yaml` | The one thing that changes for live: the Parameter Store path. |
| `install.sh` | Sets up the box: k3s, Helm, the database secrets, Airflow, the database restore, and a restart. |
| `airflow_db_backup.py` | Saves Airflow's database to S3 and restores the newest copy. |

## How the pieces fit

1. The box starts at 10:00 UTC. `install.sh` installs pinned versions of k3s and Helm.
2. It reads the database password from Parameter Store and makes two Kubernetes secrets from it. The password is sent on standard input, so it is on no command line.
3. It installs Airflow with the chart, using my image and my settings.
4. It restores the newest database backup from S3, then restarts Airflow, so the run history is back.
5. After each run and at shutdown, `airflow_db_backup.py save` writes a new backup and keeps the newest two.

The backup runs inside the PostgreSQL pod, where the password is already set, so the dump command never carries a password.

## Checking it

Everything here has a test that I wrote first.

```powershell
pytest platform/box/tests
```

- The chart tests render the real chart with Helm and check the result. They use Helm if it is installed, or Docker if it is not.
- The install script tests run the script in dry-run mode, which prints each step and runs none of them.
- To check the image, build it and run the smoke test:

```powershell
docker build --file platform/box/Dockerfile.airflow --tag portfolio-airflow:local .
bash platform/box/smoke_test_airflow_image.sh portfolio-airflow:local
```

## What is not done yet

- Spark runs inside the Airflow scheduler in local mode. Running it as separate Spark jobs through the Spark operator is the next step.
- Nothing creates an Airflow login. The API server is not exposed outside the box, and I create a user by hand through Session Manager when I need one.
- None of this has run on a real box yet. The CPU and memory limits are placeholders until I measure the real stack.
