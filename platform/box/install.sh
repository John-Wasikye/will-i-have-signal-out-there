#!/usr/bin/env bash
# Sets up the session box: k3s, Helm, and Airflow with its database restored from S3.
#
# Usage: install.sh dev|live
#
# Needs these settings in the environment:
#   IMAGE_REPOSITORY  where the Airflow image is stored
#   IMAGE_TAG         the image version to run
#   BACKUP_BUCKET     the lake bucket, which holds the Airflow database backups
#   SITE_BUCKET       the site bucket, where the pipeline publishes its files
#   ALERT_TOPIC_ARN   the run alerts topic, from the alert_topic_arn Terraform output
#
# DRY_RUN=1 prints every step and command and runs none of them. The tests use it.
set -euo pipefail

K3S_VERSION="v1.36.5+k3s1"
HELM_VERSION="v4.3.0"
AIRFLOW_CHART_VERSION="1.22.0"
NAMESPACE="airflow"

# k3s writes its connection details here. Helm and kubectl read this variable.
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

fail() {
  echo "$1" >&2
  exit 2
}

environment="${1:-}"
[[ -n "${environment}" ]] || fail "usage: install.sh dev|live"
[[ "${environment}" == "dev" || "${environment}" == "live" ]] \
  || fail "The environment must be dev or live, not '${environment}'."
for setting in IMAGE_REPOSITORY IMAGE_TAG BACKUP_BUCKET SITE_BUCKET ALERT_TOPIC_ARN; do
  [[ -n "${!setting:-}" ]] || fail "${setting} must be set."
done
# A dev box must never email through the live topic, or the reverse.
[[ "${ALERT_TOPIC_ARN}" == *":portfolio-${environment}-run-alerts" ]] \
  || fail "ALERT_TOPIC_ARN must be the ${environment} run alerts topic."
# boto3 does not read the region from the instance metadata, as the AWS CLI does, so the
# watchdog and the Airflow pods are told it. The alert topic is in the box's region.
[[ "${ALERT_TOPIC_ARN}" =~ ^arn:aws:sns:([a-z0-9-]+): ]] \
  || fail "ALERT_TOPIC_ARN must be an SNS topic ARN."
export AWS_DEFAULT_REGION="${BASH_REMATCH[1]}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dry_run="${DRY_RUN:-0}"
step_number=0

step() {
  step_number=$((step_number + 1))
  echo "STEP ${step_number}: $*"
}

# Prints a command, then runs it unless this is a dry run.
run() {
  echo "+ $*"
  if [[ "${dry_run}" != "1" ]]; then
    "$@"
  fi
}

step "let k3s sign in to the image registry"
# The image is in a private ECR repository, and an ECR password lasts 12 hours. A service
# writes a fresh one before k3s starts, at every boot. It runs here before k3s is installed,
# so k3s can pull the image on its very first start.
registry="${IMAGE_REPOSITORY%%/*}"
login_unit_path="/etc/systemd/system/ecr-registry-login.service"
login_unit_text="[Unit]
Description=Write a fresh ECR password where k3s reads it
Wants=network-online.target
After=network-online.target
Before=k3s.service

[Service]
Type=oneshot
ExecStart=${script_dir}/ecr_registry_login.sh ${registry}

[Install]
WantedBy=multi-user.target"
echo "+ write ${login_unit_path}"
echo "${login_unit_text}"
if [[ "${dry_run}" != "1" ]]; then
  printf '%s\n' "${login_unit_text}" > "${login_unit_path}"
fi
run systemctl daemon-reload
run systemctl enable --now ecr-registry-login

step "install k3s"
# The k3s installer is not checksummed, so I pin the version it installs.
run env INSTALL_K3S_VERSION="${K3S_VERSION}" \
  sh -c "curl -sfL https://get.k3s.io | sh -"

step "install helm"
run env DESIRED_VERSION="${HELM_VERSION}" \
  bash -c "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 | bash"

step "install the python tools for the box scripts"
# The database restore and the watchdog are Python scripts that run on the box itself.
run dnf install --assumeyes python3.11 python3.11-pip
run python3.11 -m pip install --requirement "${script_dir}/requirements-host.txt"

step "create the ${NAMESPACE} namespace"
run bash -c "kubectl create namespace ${NAMESPACE} --dry-run=client --output yaml | kubectl apply -f -"

step "create the database secrets from Parameter Store"
password_parameter="/portfolio/${environment}/platform/airflow-db-password"
echo "+ aws ssm get-parameter --name ${password_parameter} --with-decryption --query Parameter.Value --output text"
echo "+ kubectl apply -f - (two secrets, sent on standard input so the password is on no command line)"
if [[ "${dry_run}" != "1" ]]; then
  password="$(aws ssm get-parameter --name "${password_parameter}" --with-decryption \
    --query Parameter.Value --output text)"
  # The password goes into a connection address, so it may hold only letters and digits.
  [[ "${password}" =~ ^[A-Za-z0-9]{16,}$ ]] \
    || fail "The database password must be at least 16 letters and digits."
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: airflow-postgres
  namespace: ${NAMESPACE}
type: Opaque
stringData:
  postgres-password: ${password}
  password: ${password}
---
apiVersion: v1
kind: Secret
metadata:
  name: airflow-metadata-connection
  namespace: ${NAMESPACE}
type: Opaque
stringData:
  connection: postgresql://postgres:${password}@airflow-postgresql:5432/postgres
EOF
fi

step "create the platform settings"
# The bucket names and the topic include the AWS account number, so Airflow reads them from
# this object instead of from a file in the repository. They are not secrets.
settings_command="kubectl create configmap platform-settings --namespace ${NAMESPACE}"
settings_command+=" --from-literal PLATFORM_SITE_BUCKET=${SITE_BUCKET}"
settings_command+=" --from-literal PLATFORM_LAKE_BUCKET=${BACKUP_BUCKET}"
settings_command+=" --from-literal PLATFORM_WAREHOUSE=s3://${BACKUP_BUCKET}/warehouse"
settings_command+=" --from-literal PLATFORM_ENV=${environment}"
settings_command+=" --from-literal PLATFORM_ALERT_TOPIC_ARN=${ALERT_TOPIC_ARN}"
settings_command+=" --from-literal AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
settings_command+=" --dry-run=client --output yaml | kubectl apply -f -"
run bash -c "${settings_command}"

step "install airflow"
values_files=(--values "${script_dir}/airflow-values.yaml")
if [[ "${environment}" == "live" ]]; then
  values_files+=(--values "${script_dir}/airflow-values-live.yaml")
fi
run helm repo add apache-airflow https://airflow.apache.org
run helm upgrade --install airflow apache-airflow/airflow \
  --namespace "${NAMESPACE}" \
  --version "${AIRFLOW_CHART_VERSION}" \
  "${values_files[@]}" \
  --set "images.airflow.repository=${IMAGE_REPOSITORY}" \
  --set "images.airflow.tag=${IMAGE_TAG}" \
  --wait --timeout 15m

step "restore the database backup"
run python3.11 "${script_dir}/airflow_db_backup.py" restore --bucket "${BACKUP_BUCKET}"

step "restart airflow"
run kubectl rollout restart --namespace "${NAMESPACE}" \
  deployment/airflow-api-server deployment/airflow-dag-processor statefulset/airflow-scheduler

step "start the watchdog"
# The watchdog switches the box off when the nightly run finishes, at the 2-hour maximum, or
# when AWS sends its two-minute spot warning. It restarts if it stops, because it is a cost guard.
repo_dir="$(cd "${script_dir}/../.." && pwd)"
unit_path="/etc/systemd/system/box-watchdog.service"
unit_text="[Unit]
Description=Switch the session box off when its work is done
After=network-online.target

[Service]
Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml
Environment=AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
Environment=PYTHONPATH=${repo_dir}/pipelines/platform/publish:${script_dir}
ExecStart=/usr/bin/python3.11 ${script_dir}/box_watchdog.py --bucket ${BACKUP_BUCKET} --env ${environment} --alert-topic-arn ${ALERT_TOPIC_ARN}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target"
echo "+ write ${unit_path}"
echo "${unit_text}"
if [[ "${dry_run}" != "1" ]]; then
  printf '%s\n' "${unit_text}" > "${unit_path}"
fi
run systemctl daemon-reload
run systemctl enable --now box-watchdog
