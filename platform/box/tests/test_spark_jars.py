"""Tests for the Spark jars baked into the Airflow image (spark-jars.txt and Dockerfile.airflow).

The nightly run must not depend on Maven Central, so the image holds every jar Spark needs
(Iceberg, Kafka, S3 through Hadoop). Spark loads each jar in PySpark's jars folder at start. Each
jar is pinned by version and by SHA-1, and the build fails on a mismatch.
"""

import re
from pathlib import Path

from sample_iceberg_job import ICEBERG_AWS_PACKAGE, ICEBERG_PACKAGE

BOX = Path(__file__).resolve().parent.parent
JAR_LIST = BOX / "spark-jars.txt"
DOCKERFILE = BOX / "Dockerfile.airflow"
SMOKE_TEST = BOX / "smoke_test_airflow_image.sh"
PYSPARK_VERSION = "3.5.9"


def _jars() -> list[tuple[str, str]]:
    """Return (repository path, SHA-1) for each jar in the list."""
    lines = JAR_LIST.read_text(encoding="utf-8").splitlines()
    entries = [line.split() for line in lines if line.strip() and not line.startswith("#")]
    return [(path, sha1) for path, sha1 in entries]


def _names() -> list[str]:
    return [path.rsplit("/", 1)[1] for path, _ in _jars()]


def test_every_jar_has_a_maven_path_with_its_version_and_a_40_digit_sha1():
    assert len(_jars()) == 8
    for path, sha1 in _jars():
        *group, artifact, version, file_name = path.split("/")
        assert group and file_name == f"{artifact}-{version}.jar", path
        assert re.fullmatch(r"[0-9a-f]{40}", sha1), path


def test_the_jars_are_the_ones_pyspark_3_5_9_and_the_iceberg_packages_need():
    names = _names()

    assert f"spark-sql-kafka-0-10_2.12-{PYSPARK_VERSION}.jar" in names
    assert f"spark-token-provider-kafka-0-10_2.12-{PYSPARK_VERSION}.jar" in names
    assert "kafka-clients-3.4.1.jar" in names
    assert "commons-pool2-2.11.1.jar" in names
    assert "hadoop-aws-3.3.4.jar" in names
    assert "aws-java-sdk-bundle-1.12.262.jar" in names
    for package in (ICEBERG_PACKAGE, ICEBERG_AWS_PACKAGE):
        _, artifact, version = package.split(":")
        assert f"{artifact}-{version}.jar" in names


def test_the_image_downloads_each_jar_from_maven_central_and_checks_its_sha1():
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert "spark-jars.txt" in text
    assert "https://repo1.maven.org/maven2/" in text
    assert "sha1sum --check" in text


def test_the_jars_go_in_the_folder_the_derby_removal_uses_after_that_removal():
    text = DOCKERFILE.read_text(encoding="utf-8")

    removal = text.index("derby-*.jar")
    jars = text.index("spark-jars.txt", removal)
    assert jars > removal
    assert text.count('os.path.join(os.path.dirname(pyspark.__file__), "jars")') == 2


def test_the_image_tells_spark_the_jars_are_already_there():
    assert "ENV SPARK_JARS_IN_IMAGE=1" in DOCKERFILE.read_text(encoding="utf-8")


def test_the_smoke_test_checks_every_jar_is_in_the_image():
    text = SMOKE_TEST.read_text(encoding="utf-8")

    assert "spark-jars.txt" in text
    assert "pyspark.__file__" in text
