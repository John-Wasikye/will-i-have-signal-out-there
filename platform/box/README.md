# Session box

These are the files that run on the session box, the one computer that runs the nightly pipelines. The Terraform that creates the box is in `platform/terraform/modules/session_box`.

| File | What it does |
|---|---|
| `Dockerfile.airflow` | Builds the Airflow image: the official image, plus Java, PySpark and my pipeline code. |
| `requirements-airflow.txt` | The packages I add to that image. |
| `smoke_test_airflow_image.sh` | Checks the built image: Java is there, the imports work, the nightly DAG loads, and it does not run as root. |
| `airflow-values.yaml` | Settings for the official Airflow chart. Local executor, CPU and memory limits, connection keys from Parameter Store. |
| `airflow-values-live.yaml` | The one thing that changes for live: the Parameter Store path. |
| `install.sh` | Sets up the box: k3s, Helm, the Python tools, the database secrets, the platform settings, Airflow, the database restore, a restart, and the watchdog. |
| `requirements-host.txt` | The Python packages for the scripts that run on the box itself. |
| `airflow_db_backup.py` | Saves Airflow's database to S3 and restores the newest copy. |
| `box_watchdog.py` | Switches the box off when its work is done. |

## How the pieces fit

1. The box starts at 10:00 UTC. `install.sh` installs pinned versions of k3s and Helm, and the Python tools the box scripts need.
2. It reads the database password from Parameter Store and makes two Kubernetes secrets from it. The password is sent on standard input, so it is on no command line.
3. It puts the bucket names in a settings object, because they hold the AWS account number and stay out of the repository.
4. It installs Airflow with the chart, using my image and my settings.
5. It restores the newest database backup from S3, then restarts Airflow, so the run history is back.
6. It starts the watchdog as a system service.

The backup runs inside the PostgreSQL pod, where the password is already set, so the dump command never carries a password.

## The watchdog

The watchdog checks every 30 seconds and stops the box for the first of these reasons:

1. **AWS is taking the box back.** AWS puts a notice in the instance metadata two minutes ahead. This applies to every boot.
2. **The nightly run finished,** whether it succeeded or failed.
3. **The box has been up for 2 hours.** It records an incident for this, and for a spot warning.

To stop, it saves the database to S3 first, because that is the step with a deadline. It then records the incident if there is one, and powers the box off last. Powering off always runs, even if a save fails, so a broken step cannot leave a server billing.

Only the scheduled boot, within 30 minutes after 10:00 UTC, counts as the nightly run. A box that I start by hand is a work session, and only a spot warning stops it. Work sessions end by the 4-hour hard stop and the idle alarm. If the watchdog cannot reach Airflow, it keeps going and still stops the box at 2 hours.

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
