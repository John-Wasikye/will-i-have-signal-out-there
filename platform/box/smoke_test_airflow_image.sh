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
in_image python -c "import airflow, pyspark, pyarrow"

echo "The nightly DAG loads"
in_image python -c "import platform_skeleton_dag as m; assert m.platform_skeleton_nightly().dag_id == 'platform_skeleton_nightly'"

echo "The image does not run as root"
test "$(in_image id -un)" = "airflow"

echo "All image checks passed"
