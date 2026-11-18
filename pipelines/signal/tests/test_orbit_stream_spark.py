"""The orbit update stream on real Spark and a real Iceberg table, without Kafka (C14).

The per-batch logic and the stream wiring take a DataFrame, so these tests feed them fixed sample
frames and text files in place of a topic. A topic needs a broker, which only the box has. They
skip where pyspark is not installed; CI's "Spark tests" job runs them.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

pytest.importorskip("pyspark", reason="pyspark is not installed here")

import orbit_stream  # noqa: E402
from lake_write import contract_columns, write_run_partition  # noqa: E402
from sample_iceberg_job import CATALOG_NAME, build_spark_session  # noqa: E402

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
STREAM = CONTRACTS / "orbit_update_stream.yaml"
NAMESPACE = "platform"
RUN_DATE = date(2026, 11, 18)
DETECTED_AT = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
FETCHED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
CHANGED = f"{CATALOG_NAME}.{NAMESPACE}.orbit_changed_satellite"
GP = f"{CATALOG_NAME}.{NAMESPACE}.celestrak_gp"


def _epoch(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    session = build_spark_session("orbit_stream_tests", str(tmp_path_factory.mktemp("warehouse")))
    # A zone that is not UTC, so a test fails if the code relies on the session's zone.
    session.conf.set("spark.sql.session.timeZone", "America/Phoenix")
    yield session
    session.stop()


@pytest.fixture(autouse=True)
def _empty_tables(spark):
    spark.sql(f"DROP TABLE IF EXISTS {CHANGED}")
    spark.sql(f"DROP TABLE IF EXISTS {GP}")


def _sets(spark, *pairs):
    """A batch of (norad_cat_id, epoch) pairs as the stream delivers them."""
    schema = "norad_cat_id BIGINT, epoch_utc TIMESTAMP, fetched_at_utc TIMESTAMP"
    return spark.createDataFrame([(n, e, FETCHED_AT) for n, e in pairs], schema=schema)


def _detect(batch, run_date=RUN_DATE):
    orbit_stream.detect_changed_satellites(
        batch,
        run_date=run_date,
        detected_at=DETECTED_AT,
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
    )


def _stored(spark):
    rows = spark.table(CHANGED).orderBy("norad_cat_id", "epoch_utc").collect()
    return [(r["norad_cat_id"], r["epoch_utc"], r["previous_epoch_utc"]) for r in rows]


def test_a_satellite_new_to_the_table_is_written_with_no_previous_epoch(spark):
    _detect(_sets(spark, (101, _epoch(18))))

    assert _stored(spark) == [(101, _epoch(18), None)]


def test_a_later_epoch_is_written_with_the_latest_stored_epoch_before_it(spark):
    _detect(_sets(spark, (101, _epoch(18))))
    _detect(_sets(spark, (101, _epoch(19))), run_date=date(2026, 11, 19))

    assert _stored(spark) == [(101, _epoch(18), None), (101, _epoch(19), _epoch(18))]


def test_an_epoch_that_is_not_later_than_the_stored_one_writes_nothing(spark):
    _detect(_sets(spark, (101, _epoch(19))))
    _detect(_sets(spark, (101, _epoch(19)), (101, _epoch(18))))

    assert _stored(spark) == [(101, _epoch(19), None)]


def test_two_new_epochs_of_one_satellite_in_one_batch_chain_their_previous_epochs(spark):
    _detect(_sets(spark, (101, _epoch(18))))
    _detect(_sets(spark, (101, _epoch(20)), (101, _epoch(19))))

    assert _stored(spark) == [
        (101, _epoch(18), None),
        (101, _epoch(19), _epoch(18)),
        (101, _epoch(20), _epoch(19)),
    ]


def test_running_the_same_batch_twice_leaves_the_same_rows(spark):
    """AC-1B.2: replaying a day of updates writes the same rows."""
    batch = _sets(spark, (101, _epoch(18)), (102, _epoch(18, 6)), (102, _epoch(18, 6)))

    _detect(batch)
    first = spark.table(CHANGED).orderBy("norad_cat_id", "epoch_utc").collect()
    _detect(batch)
    second = spark.table(CHANGED).orderBy("norad_cat_id", "epoch_utc").collect()

    assert len(first) == 2
    assert second == first


def test_a_row_has_the_contract_columns_the_run_time_and_the_run_date_partition(spark):
    _detect(_sets(spark, (101, _epoch(18))))

    contract = CONTRACTS / "orbit_changed_satellite.yaml"
    columns = contract_columns(contract, "orbit_changed_satellite")
    table = spark.table(CHANGED)
    assert table.columns == [c.name for c in columns] + ["run_date"]
    row = table.collect()[0]
    assert row["detected_at_utc"] == DETECTED_AT
    assert row["fetched_at_utc"] == FETCHED_AT
    assert row["run_date"] == RUN_DATE


def _gp_row(norad: int, epoch: datetime) -> dict:
    row = {c.name: 1.5 for c in contract_columns(CONTRACTS / "celestrak_gp.yaml", "celestrak_gp")}
    return row | {
        "norad_cat_id": norad,
        "epoch_utc": epoch,
        "object_name": f"STARLINK-{norad}",
        "source_url": "https://example.test/gp",
        "fetched_at_utc": FETCHED_AT,
        "content_sha256": "a" * 64,
    }


def _load_gp(spark, run_date, *pairs):
    write_run_partition(
        spark,
        "celestrak_gp",
        [_gp_row(n, e) for n, e in pairs],
        run_date,
        columns=contract_columns(CONTRACTS / "celestrak_gp.yaml", "celestrak_gp"),
        namespace=NAMESPACE,
    )


def _messages(spark, run_date):
    return orbit_stream.element_set_messages(
        spark, run_date, contracts_dir=CONTRACTS, namespace=NAMESPACE
    )


def test_the_first_night_publishes_every_element_set(spark):
    _load_gp(spark, RUN_DATE, (101, _epoch(18)), (102, _epoch(18)))

    assert _messages(spark, RUN_DATE).count() == 2


def test_a_later_night_publishes_only_new_satellites_and_later_epochs(spark):
    _load_gp(spark, RUN_DATE, (101, _epoch(18)), (102, _epoch(18)))
    next_day = date(2026, 11, 19)
    _load_gp(spark, next_day, (101, _epoch(18)), (102, _epoch(19)), (103, _epoch(19)))

    keys = sorted(row["key"] for row in _messages(spark, next_day).collect())

    assert keys == ["102", "103"]


def test_publishing_a_night_again_gives_the_same_messages(spark):
    _load_gp(spark, RUN_DATE, (101, _epoch(18)))
    next_day = date(2026, 11, 19)
    _load_gp(spark, next_day, (101, _epoch(19)))

    first = sorted(r["value"] for r in _messages(spark, next_day).collect())
    second = sorted(r["value"] for r in _messages(spark, next_day).collect())

    assert first == second
    assert len(first) == 1


def test_a_message_has_the_catalog_number_as_its_key_and_utc_json_as_its_value(spark):
    _load_gp(spark, RUN_DATE, (101, _epoch(18, 9)))

    row = _messages(spark, RUN_DATE).collect()[0]

    assert row["key"] == "101"
    value = json.loads(row["value"])
    assert list(value) == ["norad_cat_id", "epoch_utc", "fetched_at_utc", "elements"]
    assert value["epoch_utc"] == "2026-11-18T09:00:00.000Z"
    assert value["fetched_at_utc"] == "2026-11-18T09:00:00.000Z"
    assert list(value["elements"]) == orbit_stream.element_names(STREAM)
    assert value["elements"]["object_name"] == "STARLINK-101"


def test_the_reader_gets_back_what_the_publisher_wrote(spark):
    _load_gp(spark, RUN_DATE, (101, _epoch(18, 9)))
    raw = _messages(spark, RUN_DATE).selectExpr("CAST(value AS BINARY) AS value")

    parsed = orbit_stream.parse_messages(raw, STREAM).collect()

    assert [(r["norad_cat_id"], r["epoch_utc"], r["fetched_at_utc"]) for r in parsed] == [
        (101, _epoch(18, 9), FETCHED_AT)
    ]


def test_a_message_without_a_catalog_number_an_epoch_or_a_pull_time_is_left_out(spark):
    """The watermark runs on the pull time, so every required field is checked before writing."""
    whole = '{"norad_cat_id": 101, "epoch_utc": "2026-11-18T09:00:00.000Z", '
    whole += '"fetched_at_utc": "2026-11-18T09:00:00.000Z", "elements": {}}'
    values = [
        whole,
        '{"epoch_utc": "2026-11-18T09:00:00.000Z", "fetched_at_utc": "2026-11-18T09:00:00.000Z"}',
        '{"norad_cat_id": 102, "fetched_at_utc": "2026-11-18T09:00:00.000Z"}',
        '{"norad_cat_id": 103, "epoch_utc": "2026-11-18T09:00:00.000Z"}',
    ]
    raw = spark.createDataFrame([(v,) for v in values], "value STRING")

    parsed = orbit_stream.parse_messages(raw, STREAM).collect()

    assert [r["norad_cat_id"] for r in parsed] == [101]


def _write_messages(folder: Path, *pairs, fetched_at=FETCHED_AT, name="messages.json") -> None:
    """Write messages as JSON lines, one file per pull, the way the topic would hold them."""
    folder.mkdir(exist_ok=True)
    stamp = "%Y-%m-%dT%H:%M:%S.000Z"
    lines = [
        json.dumps(
            {
                "norad_cat_id": norad,
                "epoch_utc": epoch.strftime(stamp),
                "fetched_at_utc": fetched_at.strftime(stamp),
                "elements": {"object_name": f"STARLINK-{norad}"},
            }
        )
        for norad, epoch in pairs
    ]
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _process(spark, folder: Path, checkpoint: Path) -> None:
    raw = spark.readStream.format("text").load(folder.as_uri())
    orbit_stream.process_stream(
        raw,
        RUN_DATE,
        DETECTED_AT,
        checkpoint=checkpoint.as_uri(),
        contracts_dir=CONTRACTS,
        namespace=NAMESPACE,
    )


def test_the_stream_drops_a_duplicate_message_and_writes_each_change_once(spark, tmp_path):
    _write_messages(tmp_path / "in", (101, _epoch(18)), (101, _epoch(18)), (102, _epoch(18, 1)))

    _process(spark, tmp_path / "in", tmp_path / "checkpoint")

    assert _stored(spark) == [(101, _epoch(18), None), (102, _epoch(18, 1), None)]


def test_replaying_the_same_messages_with_a_new_checkpoint_writes_the_same_rows(spark, tmp_path):
    """AC-1B.2 through the whole stream: a day of updates read again gives the same rows."""
    _write_messages(tmp_path / "in", (101, _epoch(18)), (102, _epoch(18, 1)))

    _process(spark, tmp_path / "in", tmp_path / "first")
    first = spark.table(CHANGED).orderBy("norad_cat_id").collect()
    _process(spark, tmp_path / "in", tmp_path / "second")
    second = spark.table(CHANGED).orderBy("norad_cat_id").collect()

    assert len(first) == 2
    assert second == first


def test_a_later_night_keeps_an_update_whose_epoch_is_older_than_last_nights_newest(
    spark, tmp_path
):
    """Epochs are spread over a day or more, so the watermark must follow the pull time.

    Night 1 holds an epoch at 23:00 on Nov 17. Night 2 brings satellite 102 an epoch at 05:00 on
    Nov 17, later than its stored 01:00 but far more than 2 hours before 23:00. A watermark on the
    epoch would drop it for good; on the pull time it is kept.
    """
    night_one = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    _write_messages(
        tmp_path / "in",
        (101, _epoch(17, 23)),
        (102, _epoch(17, 1)),
        fetched_at=night_one,
        name="night1.json",
    )
    _process(spark, tmp_path / "in", tmp_path / "checkpoint")
    _write_messages(tmp_path / "in", (102, _epoch(17, 5)), name="night2.json")

    _process(spark, tmp_path / "in", tmp_path / "checkpoint")

    assert (102, _epoch(17, 5), _epoch(17, 1)) in _stored(spark)
