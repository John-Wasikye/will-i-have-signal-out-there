"""Tests for kafka.yaml, the manifest that runs one Kafka broker on the session box.

The orbit update stream (C14, ADR 0016) needs a topic that holds a day of element sets until the
streaming job reads them. I read the manifest as data and check the choices that matter: the
image is pinned by digest, the broker runs alone in KRaft mode (Kafka's own metadata quorum, no
ZooKeeper), the log is on a persistent volume and is kept for 7 days.
"""

from pathlib import Path

import pytest
import yaml

MANIFEST = Path(__file__).resolve().parent.parent / "kafka.yaml"
IMAGE = "apache/kafka:4.4.0@sha256:833b867a9585a141da455dc2b57431c65cbccb27f11c91f694444cca9f777e0f"


@pytest.fixture(scope="module")
def objects() -> dict[str, dict]:
    """Return the manifest's objects by kind."""
    documents = [d for d in yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")) if d]
    return {document["kind"]: document for document in documents}


@pytest.fixture(scope="module")
def container(objects) -> dict:
    return objects["Deployment"]["spec"]["template"]["spec"]["containers"][0]


@pytest.fixture(scope="module")
def settings(container) -> dict[str, str]:
    return {item["name"]: item["value"] for item in container["env"]}


def test_every_object_is_in_the_kafka_namespace(objects):
    assert objects["Namespace"]["metadata"]["name"] == "kafka"
    for kind in ("PersistentVolumeClaim", "Deployment", "Service"):
        assert objects[kind]["metadata"]["namespace"] == "kafka", kind


def test_the_image_is_the_official_one_pinned_by_digest(container):
    assert container["image"] == IMAGE


def test_one_broker_is_also_the_controller_in_kraft_mode(settings):
    assert settings["KAFKA_PROCESS_ROLES"] == "broker,controller"
    assert settings["KAFKA_CONTROLLER_QUORUM_VOTERS"] == "1@localhost:9093"
    assert "KAFKA_ZOOKEEPER_CONNECT" not in settings


def test_the_internal_topics_keep_one_copy_because_there_is_one_broker(settings):
    for name in (
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR",
        "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR",
        "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR",
    ):
        assert settings[name] == "1", name


def test_the_log_is_kept_for_seven_days(settings):
    assert settings["KAFKA_LOG_RETENTION_HOURS"] == str(7 * 24)


def test_the_broker_heap_is_one_gigabyte_inside_a_larger_memory_limit(container, settings):
    assert settings["KAFKA_HEAP_OPTS"] == "-Xms1g -Xmx1g"
    assert container["resources"]["limits"]["memory"] == "1536Mi"


def test_the_service_listens_on_9092_and_the_broker_advertises_its_address(objects, settings):
    service = objects["Service"]
    assert service["metadata"]["name"] == "kafka"
    assert [port["port"] for port in service["spec"]["ports"]] == [9092]
    assert (
        settings["KAFKA_ADVERTISED_LISTENERS"] == "PLAINTEXT://kafka.kafka.svc.cluster.local:9092"
    )


def test_the_log_is_on_a_persistent_volume_claim_on_the_box_disk(objects, container, settings):
    claim = objects["PersistentVolumeClaim"]
    volumes = objects["Deployment"]["spec"]["template"]["spec"]["volumes"]
    assert [v["persistentVolumeClaim"]["claimName"] for v in volumes] == [claim["metadata"]["name"]]
    mount = container["volumeMounts"][0]
    assert mount["name"] == volumes[0]["name"]
    assert settings["KAFKA_LOG_DIRS"].startswith(mount["mountPath"])
    assert claim["spec"]["accessModes"] == ["ReadWriteOnce"]


def test_the_single_broker_is_stopped_before_a_new_one_starts(objects):
    """Two brokers on one volume would corrupt it, so an update stops the old pod first."""
    assert objects["Deployment"]["spec"]["strategy"]["type"] == "Recreate"


def test_airflow_is_told_the_address_the_service_and_the_broker_use(settings):
    values = yaml.safe_load((MANIFEST.parent / "airflow-values.yaml").read_text(encoding="utf-8"))
    address = {item["name"]: item["value"] for item in values["env"]}["SIGNAL_KAFKA_BOOTSTRAP"]

    assert address == "kafka.kafka.svc.cluster.local:9092"
    assert settings["KAFKA_ADVERTISED_LISTENERS"] == f"PLAINTEXT://{address}"
