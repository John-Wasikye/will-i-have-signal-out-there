#!/usr/bin/env bash
# Sets up the session box: k3s, Helm, and Airflow with its database restored from S3.
#
# Usage: install.sh dev|live
#
# Needs these settings in the environment:
#   IMAGE_REPOSITORY  where the Airflow image is stored
#   IMAGE_TAG         the image version to run
#   BACKUP_BUCKET     the S3 bucket that holds the Airflow database backups
#
# DRY_RUN=1 prints every step and command and runs none of them. The tests use it.
set -euo pipefail

K3S_VERSION="v1.36.5+k3s1"
HELM_VERSION="v4.3.0"
AIRFLOW_CHART_VERSION="1.22.0"
NAMESPACE="airflow"

fail() {
  echo "$1" >&2
  exit 2
}

environment="${1:-}"
[[ -n "${environment}" ]] || fail "usage: install.sh dev|live"
[[ "${environment}" == "dev" || "${environment}" == "live" ]] \
  || fail "The environment must be dev or live, not '${environment}'."
for setting in IMAGE_REPOSITORY IMAGE_TAG BACKUP_BUCKET; do
  [[ -n "${!setting:-}" ]] || fail "${setting} must be set."
done

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

step "install k3s"
# The k3s installer is not checksummed, so I pin the version it installs.
run env INSTALL_K3S_VERSION="${K3S_VERSION}" \
  sh -c "curl -sfL https://get.k3s.io | sh -"

step "install helm"
run env DESIRED_VERSION="${HELM_VERSION}" \
  bash -c "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 | bash"

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
