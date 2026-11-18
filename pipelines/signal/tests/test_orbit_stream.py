"""Tests for the orbit update stream's plain-Python parts (C14, ADR 0016, ADR 0028).

Spark and Kafka are not needed here. The Spark parts (publishing, parsing, finding the changed
satellites) are in test_orbit_stream_spark.py, which runs in CI. The task functions in
signal_nightly are checked with the stream functions replaced.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import orbit_stream
import signal_nightly

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
STREAM = CONTRACTS / "orbit_update_stream.yaml"


def test_the_topic_the_watermark_and_the_table_are_the_ones_john_approved():
    assert orbit_stream.TOPIC == "orbit-element-sets"
    assert orbit_stream.WATERMARK == "2 hours"
    assert orbit_stream.CHANGED_TABLE == "orbit_changed_satellite"


def test_kafka_is_found_at_its_address_on_the_box_unless_the_environment_says_otherwise():
    assert orbit_stream.kafka_bootstrap({}) == "kafka.kafka.svc.cluster.local:9092"
    assert orbit_stream.kafka_bootstrap({"SIGNAL_KAFKA_BOOTSTRAP": "k:1"}) == "k:1"


def test_the_checkpoint_goes_to_the_lake_bucket_under_the_environments_folder():
    """v2: the move to one state partition needs a new checkpoint (Spark keeps the old count)."""
    assert orbit_stream.checkpoint_location("portfolio-dev-lake-123456789012", "dev") == (
        "s3a://portfolio-dev-lake-123456789012/checkpoints/orbit-element-sets/dev/v2/"
    )


def test_the_message_schema_is_written_out_from_the_contract():
    assert orbit_stream.message_schema(STREAM) == (
        "norad_cat_id BIGINT, epoch_utc TIMESTAMP, fetched_at_utc TIMESTAMP, "
        "elements STRUCT<object_name: STRING, inclination_deg: DOUBLE, "
        "mean_motion_rev_per_day: DOUBLE, eccentricity: DOUBLE, ra_of_asc_node_deg: DOUBLE, "
        "arg_of_pericenter_deg: DOUBLE, mean_anomaly_deg: DOUBLE, bstar: DOUBLE>"
    )


def test_the_element_names_are_the_contracts_in_order():
    assert orbit_stream.element_names(STREAM) == [
        "object_name",
        "inclination_deg",
        "mean_motion_rev_per_day",
        "eccentricity",
        "ra_of_asc_node_deg",
        "arg_of_pericenter_deg",
        "mean_anomaly_deg",
        "bstar",
    ]


def test_the_publish_task_returns_how_many_element_sets_it_published(monkeypatch):
    calls = []

    def fake_publish(spark, run_date, **settings):
        calls.append((spark, run_date, settings))
        return 7

    monkeypatch.setattr(signal_nightly, "publish_element_sets", fake_publish)

    result = signal_nightly.publish_orbit_updates(
        "spark", date(2026, 11, 18), contracts_dir=CONTRACTS, namespace="n", bootstrap="k:1"
    )

    assert result == {"published": 7}
    assert calls == [
        (
            "spark",
            date(2026, 11, 18),
            {"contracts_dir": CONTRACTS, "namespace": "n", "bootstrap": "k:1"},
        )
    ]


def test_the_changed_task_returns_how_many_satellites_changed(monkeypatch):
    seen = {}

    def fake_run(spark, run_date, detected_at, **settings):
        seen.update(settings, detected_at=detected_at)
        return 3

    monkeypatch.setattr(signal_nightly, "run_orbit_stream", fake_run)
    when = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)

    result = signal_nightly.find_changed_satellites(
        "spark",
        date(2026, 11, 18),
        when,
        contracts_dir=CONTRACTS,
        namespace="n",
        bootstrap="k:1",
        checkpoint="s3a://b/c/",
    )

    assert result == {"changed": 3}
    assert seen["detected_at"] == when
    assert seen["checkpoint"] == "s3a://b/c/"
