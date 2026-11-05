#!/usr/bin/env bash
# Checks that the Airflow image has everything the nightly DAG needs.
# Usage: smoke_test_airflow_image.sh IMAGE
set -euo pipefail

image="${1:?usage: smoke_test_airflow_image.sh IMAGE}"

# Run one command inside the image, without the image's own start-up script.
in_image() {
  docker run --rm --entrypoint "" "${image}" "$@"
}

echo "Java is installed, because Spark needs it"
in_image java -version

echo "Airflow, PySpark and PyArrow import"
in_image python -c "import airflow, pyspark, pyarrow, numpy, sgp4, h3"

echo "The nightly DAG loads"
in_image python -c "import platform_skeleton_dag as m; assert m.platform_skeleton_nightly().dag_id == 'platform_skeleton_nightly'"

echo "The signal DAG loads"
in_image python -c "import signal_phase_a_dag as m; assert m.signal_phase_a_nightly().dag_id == 'signal_phase_a_nightly'"

echo "Airflow reads exactly the two DAG files from its DAG folder"
in_image python -c "
import os
from airflow.utils.file import list_py_file_paths
found = sorted(os.path.relpath(path, os.environ['AIRFLOW__CORE__DAGS_FOLDER']) for path in list_py_file_paths(os.environ['AIRFLOW__CORE__DAGS_FOLDER']))
assert found == ['platform/dags/platform_skeleton_dag.py', 'signal/dags/signal_phase_a_dag.py'], found
"

echo "The signal pipeline modules import"
in_image python -c "import contract_diff, dtc_selector, lake_write, orbit_ingest, raw_store, trail_loader"

echo "The signal pipelines' contracts are in the image"
# shellcheck disable=SC2016  # The variable is set in the image, so it expands there, not here.
in_image bash -c 'for table in celestrak_gp nps_trails trail_point dtc_satellite dtc_disagreement; do test -f "${SIGNAL_CONTRACTS_DIR}/${table}.yaml"; done'

echo "dbt runs from its own environment and reads the project"
# shellcheck disable=SC2016  # The variables are set in the image, so they expand there, not here.
in_image bash -c 'mkdir -p /tmp/dbt-smoke && SIGNAL_DBT_INPUT_DIR=/tmp/dbt-smoke SIGNAL_DBT_OUTPUT_DIR=/tmp/dbt-smoke SIGNAL_DBT_WORK_DIR=/tmp/dbt-smoke DBT_TARGET_PATH=/tmp/dbt-smoke/target DBT_LOG_PATH=/tmp/dbt-smoke/logs DBT_PROFILES_DIR="${SIGNAL_DBT_PROJECT_DIR}" "${SIGNAL_DBT_BIN}" parse --project-dir "${SIGNAL_DBT_PROJECT_DIR}"'

echo "The image does not run as root"
test "$(in_image id -un)" = "airflow"

echo "All image checks passed"
