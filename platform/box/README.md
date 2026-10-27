# Session box

These are the files that run on the session box, the one computer that runs the nightly pipelines. The Terraform that creates the box is in `platform/terraform/modules/session_box`.

| File | What it does |
|---|---|
| `Dockerfile.airflow` | Builds the Airflow image: the official image, plus Java, PySpark and my pipeline code. |
| `requirements-airflow.txt` | The packages I add to that image. |
| `smoke_test_airflow_image.sh` | Checks the built image: Java is there, the imports work, the nightly DAG loads, and it does not run as root. |
| `airflow-values.yaml` | Settings for the official Airflow chart. Local executor, CPU and memory limits, connection keys from Parameter Store. |
| `airflow-values-live.yaml` | The one thing that changes for live: the Parameter Store path. |
| `install.sh` | Sets up the box: the image registry sign-in, k3s, Helm, the Python tools, the database secrets, the platform settings, Airflow, the database restore, a restart, and the watchdog. |
| `ecr_registry_login.sh` | Writes a fresh ECR password where k3s reads it, so k3s can pull my image from the private repository. A service runs it before k3s at every boot. |
| `requirements-host.txt` | The Python packages for the scripts that run on the box itself. |
| `airflow_db_backup.py` | Saves Airflow's database to S3 and restores the newest copy. |
| `box_watchdog.py` | Switches the box off when its work is done. |

## How the pieces fit

1. The box starts at 10:00 UTC. `install.sh` first sets up the image registry sign-in: the image is in a private ECR repository, and an ECR password lasts 12 hours, so a service writes a fresh one before k3s starts, at every boot. It then installs pinned versions of k3s and Helm, and the Python tools the box scripts need.
2. It reads the database password from Parameter Store and makes two Kubernetes secrets from it. The password is sent on standard input, so it is on no command line.
3. It puts the bucket names, the environment name and the run alerts topic in a settings object, because they hold the AWS account number and stay out of the repository. It refuses a topic from the other environment.
4. It installs Airflow with the chart, using my image and my settings.
5. It restores the newest database backup from S3, then restarts Airflow, so the run history is back.
6. It starts the watchdog as a system service.

The backup runs inside the PostgreSQL pod, where the password is already set, so the dump command never carries a password.

## The watchdog

The watchdog checks every 30 seconds and stops the box for the first of these reasons:

1. **AWS is taking the box back.** AWS puts a notice in the instance metadata two minutes ahead. This applies to every boot.
2. **The nightly run finished,** whether it succeeded or failed.
3. **The box has been up for 2 hours.** It records an incident for this, and for a spot warning, and emails me through the run alerts topic, because a run stopped this way never reports anything itself.

To stop, it saves the database to S3 first, because that is the step with a deadline. It then records the incident and sends the email if there is one, and powers the box off last. Powering off always runs, even if a save fails, so a broken step cannot leave a server billing.

Only a boot between 10:00 and 12:00 UTC counts as the nightly run, because the start schedule retries for up to 2 hours when AWS has no spot capacity. If the watchdog cannot reach Airflow, it keeps going and still stops the box at 2 hours.

Any other boot is either a work session I planned or a start nobody planned. After AWS takes a spot box back, it starts the box again by itself once capacity returns, at any hour; on 2026-10-26 it did so at 15:52 UTC. So a work session has to be marked: before I start the box, I tag it with `WorkSessionUntil`, the time the session ends. The watchdog reads that tag from the instance metadata on every check.

- **A boot with no tag, or with a tag from an earlier session,** is a start nobody planned. The watchdog saves the database, emails me, and powers off at once.
- **A work session** stops at its tagged end time, at the 4-hour session limit counted from its boot, or for a spot warning, whichever comes first. The idle alarm also stops it after 30 idle minutes. I can change the tag during the session to end it sooner. If the tag cannot be read, the session gets the 4-hour limit, so a failed read never cuts a session short.

The 14:00 UTC hard stop only bounds the nightly run, so without these limits a box started in the evening would run until the next afternoon.

To start a work session, in PowerShell (the instance ID is the `session_box_instance_id` Terraform output):

```powershell
$env:AWS_PROFILE = "nfl_player_stats"
$box = "<instance id>"
$until = (Get-Date).ToUniversalTime().AddHours(4).ToString("yyyy-MM-ddTHH:mm:ssZ")
aws ec2 create-tags --resources $box --tags "Key=WorkSessionUntil,Value=$until"
aws ec2 start-instances --instance-ids $box
```

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
