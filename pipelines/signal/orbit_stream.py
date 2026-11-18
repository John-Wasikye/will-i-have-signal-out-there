"""Orbit update stream (C14): publish new element sets to Kafka, find the changed satellites.

Kafka (a message queue) runs only while the session box is on, and this stream is low-rate by
streaming standards (ADR 0016): one batch a night of about 11,000 small messages, one per
satellite whose element set CelesTrak refreshed (10,872 on the first night, Nov 18, 2026).
Two steps, each a task of the nightly DAG:

1. ``publish_element_sets`` writes the run date's new element sets from ``celestrak_gp`` to the
   topic. An element set is new when its epoch is later than every earlier partition's epoch for
   that satellite, or the satellite is not in an earlier partition. The key is the catalog number
   as text and the value is JSON as in contracts/orbit_update_stream.yaml.
2. ``run_orbit_stream`` reads the topic with Structured Streaming (Spark's streaming engine)
   and the availableNow trigger: it processes everything new since the last run, then stops. It
   reads the messages with an explicit schema, drops a duplicate within the 2-hour watermark, and
   hands each batch to ``detect_changed_satellites``. A satellite is changed when a new element
   set has a later epoch than the last one stored for its catalog number (ADR 0028).

``detect_changed_satellites`` writes ``orbit_changed_satellite`` with a MERGE on (norad_cat_id,
epoch_utc) and keeps only epochs later than the stored latest, so reading the same messages again
writes the same rows (AC-1B.2). The run's time is passed in for the same reason.

The 2-hour watermark (ADR 0028, the nightly maximum) runs on the pull time, ``fetched_at_utc``,
which moves forward once a night. It cannot run on the epoch: epochs are spread over a day or
more, the watermark is kept in the checkpoint, and Spark would drop for good any update whose
epoch is more than 2 hours older than the newest epoch it had seen, even on an earlier night.

The checkpoint path is on S3 (``s3a://``), so it must be readable by Spark: the image has the
Hadoop S3 jars and the box's instance role is the credential (platform/box/spark-jars.txt).

Timestamps in messages are UTC text with a Z, written and read with the same options, so the
session's time zone never changes a message.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import yaml
from lake_write import SPARK_TYPES, contract_columns, spark_schema
from sample_iceberg_job import CATALOG_NAME
from timeutil import require_utc

TOPIC = "orbit-element-sets"
WATERMARK = "2 hours"
# A nightly batch of about 11,000 small messages needs one state store; Spark's default 200 would
# write about 400 tiny files to S3 a night.
STATE_PARTITIONS = "1"
# Spark keeps the partition count inside a checkpoint and ignores a new setting, so the move to one
# partition (Nov 18, 2026) starts a new checkpoint folder. The stream then reads the topic again
# from the start, and the MERGE writes the same rows (AC-1B.2).
CHECKPOINT_VERSION = "v2"
CHANGED_TABLE = "orbit_changed_satellite"
SOURCE_TABLE = "celestrak_gp"
DEFAULT_BOOTSTRAP = "kafka.kafka.svc.cluster.local:9092"
JSON_OPTIONS = {"timestampFormat": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX", "timeZone": "UTC"}
CANDIDATES_VIEW = "orbit_changed_candidates"


def kafka_bootstrap(environ: Mapping[str, str]) -> str:
    """Return Kafka's address: SIGNAL_KAFKA_BOOTSTRAP, else the broker on the box."""
    return environ.get("SIGNAL_KAFKA_BOOTSTRAP", DEFAULT_BOOTSTRAP)


def checkpoint_location(lake_bucket: str, environment: str) -> str:
    """Return where the stream keeps its checkpoints, under the lake bucket (ADR 0016)."""
    return f"s3a://{lake_bucket}/checkpoints/{TOPIC}/{environment}/{CHECKPOINT_VERSION}/"


def _message_properties(contract_path: Path) -> list[dict]:
    contract = yaml.safe_load(Path(contract_path).read_text(encoding="utf-8"))
    return next(t for t in contract["schema"] if t["name"] == "orbit_update_stream")["properties"]


def message_schema(contract_path: Path) -> str:
    """Return the Spark DDL schema of a message's value, written out from the contract."""
    return ", ".join(
        f"{prop['name']} {_message_type(prop)}" for prop in _message_properties(contract_path)
    )


def _message_type(prop: dict) -> str:
    if prop["logicalType"] != "object":
        return SPARK_TYPES[prop["logicalType"]]
    inner = ", ".join(f"{p['name']}: {SPARK_TYPES[p['logicalType']]}" for p in prop["properties"])
    return f"STRUCT<{inner}>"


def element_names(contract_path: Path) -> list[str]:
    """Return the names of the orbital elements inside a message, in the contract's order."""
    elements = next(p for p in _message_properties(contract_path) if p["name"] == "elements")
    return [prop["name"] for prop in elements["properties"]]


def new_element_sets(frame, run_date: date):  # noqa: ANN001, ANN201, a celestrak_gp DataFrame
    """Return the run date's element sets that are later than any earlier partition's."""
    from pyspark.sql import functions as F

    today = date(run_date.year, run_date.month, run_date.day)
    earlier = (
        frame.where(F.col("run_date") < F.lit(today))
        .groupBy("norad_cat_id")
        .agg(F.max("epoch_utc").alias("earlier_epoch"))
    )
    return (
        frame.where(F.col("run_date") == F.lit(today))
        .join(earlier, "norad_cat_id", "left")
        .where(F.col("earlier_epoch").isNull() | (F.col("epoch_utc") > F.col("earlier_epoch")))
        .drop("earlier_epoch")
    )


def element_set_messages(spark, run_date: date, *, contracts_dir: Path, namespace: str):  # noqa: ANN001, ANN201
    """Return the run date's new element sets as Kafka messages: a ``key`` and a ``value``."""
    from pyspark.sql import functions as F

    contract = Path(contracts_dir) / "orbit_update_stream.yaml"
    sets = new_element_sets(spark.table(f"{CATALOG_NAME}.{namespace}.{SOURCE_TABLE}"), run_date)
    elements = F.struct(*element_names(contract)).alias("elements")
    message = F.struct("norad_cat_id", "epoch_utc", "fetched_at_utc", elements)
    return sets.select(
        F.col("norad_cat_id").cast("string").alias("key"),
        F.to_json(message, JSON_OPTIONS).alias("value"),
    )


def publish_element_sets(
    spark,  # noqa: ANN001, a pyspark SparkSession
    run_date: date,
    *,
    contracts_dir: Path,
    namespace: str,
    bootstrap: str,
) -> int:
    """Write the run date's new element sets to the topic and return how many there were.

    Publishing a night again sends the same messages again. The stream job drops the copies.
    """
    messages = element_set_messages(
        spark, run_date, contracts_dir=contracts_dir, namespace=namespace
    )
    count = messages.count()
    messages.write.format("kafka").option("kafka.bootstrap.servers", bootstrap).option(
        "topic", TOPIC
    ).save()
    return count


def parse_messages(raw, contract_path: Path):  # noqa: ANN001, ANN201, a DataFrame with ``value``
    """Return each message's catalog number, epoch and pull time, read with the explicit schema.

    A message that is not JSON of that shape, or has no catalog number, epoch or pull time, is
    left out: the watermark runs on the pull time, and the table relies on this check.
    """
    from pyspark.sql import functions as F

    parsed = F.from_json(F.col("value").cast("string"), message_schema(contract_path), JSON_OPTIONS)
    return (
        raw.select(parsed.alias("message"))
        .select("message.norad_cat_id", "message.epoch_utc", "message.fetched_at_utc")
        .where(
            F.col("norad_cat_id").isNotNull()
            & F.col("epoch_utc").isNotNull()
            & F.col("fetched_at_utc").isNotNull()
        )
    )


def detect_changed_satellites(
    batch,  # noqa: ANN001, a DataFrame of norad_cat_id, epoch_utc and fetched_at_utc
    *,
    run_date: date,
    detected_at: datetime,
    contracts_dir: Path,
    namespace: str,
) -> None:
    """Write the batch's changed satellites to ``orbit_changed_satellite``.

    A row is written only when its epoch is later than the latest epoch stored for the satellite,
    or the satellite is new. ``previous_epoch_utc`` is that stored epoch, or the batch's own
    earlier epoch when a satellite has two new ones. The MERGE inserts rows whose
    (norad_cat_id, epoch_utc) is not stored yet. The table is made with optional columns, because
    Iceberg refuses a MERGE source that Spark cannot prove is never null; the stream keeps null
    keys out (``parse_messages``).
    """
    from pyspark.sql import Window
    from pyspark.sql import functions as F

    spark = batch.sparkSession
    columns = contract_columns(Path(contracts_dir) / f"{CHANGED_TABLE}.yaml", CHANGED_TABLE)
    full_name = f"{CATALOG_NAME}.{namespace}.{CHANGED_TABLE}"
    if not spark.catalog.tableExists(full_name):
        optional = [replace(column, required=False) for column in columns]
        empty = spark.createDataFrame([], schema=spark_schema(optional))
        empty.writeTo(full_name).partitionedBy("run_date").create()

    stored = spark.table(full_name).groupBy("norad_cat_id").agg(F.max("epoch_utc").alias("stored"))
    later = (
        batch.dropDuplicates(["norad_cat_id", "epoch_utc"])
        .join(stored, "norad_cat_id", "left")
        .where(F.col("stored").isNull() | (F.col("epoch_utc") > F.col("stored")))
    )
    in_order = Window.partitionBy("norad_cat_id").orderBy("epoch_utc")
    plain_date = date(run_date.year, run_date.month, run_date.day)
    later.select(
        "norad_cat_id",
        "epoch_utc",
        F.coalesce(F.lag("epoch_utc").over(in_order), F.col("stored")).alias("previous_epoch_utc"),
        "fetched_at_utc",
        F.lit(require_utc(detected_at, "detected_at")).alias("detected_at_utc"),
        F.lit(plain_date).alias("run_date"),
    ).createOrReplaceTempView(CANDIDATES_VIEW)
    spark.sql(
        f"MERGE INTO {full_name} AS target USING {CANDIDATES_VIEW} AS source "
        "ON target.norad_cat_id = source.norad_cat_id AND target.epoch_utc = source.epoch_utc "
        "WHEN NOT MATCHED THEN INSERT *"
    )


def process_stream(
    raw,  # noqa: ANN001, a streaming DataFrame with a ``value`` column, as Kafka gives it
    run_date: date,
    detected_at: datetime,
    *,
    checkpoint: str,
    contracts_dir: Path,
    namespace: str,
) -> None:
    """Read everything new in the stream, find the changed satellites, then stop."""
    contract = Path(contracts_dir) / "orbit_update_stream.yaml"
    raw.sparkSession.conf.set("spark.sql.shuffle.partitions", STATE_PARTITIONS)
    unique = (
        parse_messages(raw, contract)
        .withWatermark("fetched_at_utc", WATERMARK)
        .dropDuplicatesWithinWatermark(["norad_cat_id", "epoch_utc"])
    )

    def write_batch(batch, batch_id: int) -> None:  # noqa: ANN001, ARG001
        detect_changed_satellites(
            batch,
            run_date=run_date,
            detected_at=detected_at,
            contracts_dir=contracts_dir,
            namespace=namespace,
        )

    query = (
        unique.writeStream.trigger(availableNow=True)
        .option("checkpointLocation", checkpoint)
        .foreachBatch(write_batch)
        .start()
    )
    query.awaitTermination()


def run_orbit_stream(
    spark,  # noqa: ANN001, a pyspark SparkSession
    run_date: date,
    detected_at: datetime,
    *,
    bootstrap: str,
    checkpoint: str,
    contracts_dir: Path,
    namespace: str,
) -> int:
    """Read the topic from the checkpoint on, and return the changed satellites of the run date.

    The checkpoint path must be readable by Spark, which is why it is an ``s3a://`` path here.
    """
    from pyspark.sql import functions as F

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", TOPIC)
        .option("startingOffsets", "earliest")
        .load()
    )
    process_stream(
        raw,
        run_date,
        detected_at,
        checkpoint=checkpoint,
        contracts_dir=contracts_dir,
        namespace=namespace,
    )
    full_name = f"{CATALOG_NAME}.{namespace}.{CHANGED_TABLE}"
    if not spark.catalog.tableExists(full_name):
        return 0
    plain_date = date(run_date.year, run_date.month, run_date.day)
    return spark.table(full_name).where(F.col("run_date") == F.lit(plain_date)).count()
