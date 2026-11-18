"""Tests for the orbit stream contracts (C14): the Kafka message and the changed-satellite table.

Both are proposals waiting for John. The code reads its columns from them, so these tests keep the
message's element fields equal to the celestrak_gp columns they come from.
"""

from pathlib import Path

import yaml
from lake_write import contract_columns

CONTRACTS = Path(__file__).parents[3] / "docs" / "trip-planner" / "contracts"
STREAM = CONTRACTS / "orbit_update_stream.yaml"
TABLE = CONTRACTS / "orbit_changed_satellite.yaml"
# The celestrak_gp columns that are not orbital elements: the key, the time, and the pull's facts.
NOT_ELEMENTS = {"norad_cat_id", "epoch_utc", "source_url", "fetched_at_utc", "content_sha256"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _server_settings(contract: dict) -> dict[str, str]:
    server = contract["servers"][0]
    return {item["property"]: item["value"] for item in server["customProperties"]}


def test_both_contracts_are_approved_at_the_versions_this_change_builds():
    for path, version in ((STREAM, "0.2.0"), (TABLE, "0.1.0")):
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert f"{version} approved by John (Nov 18, 2026)" in first_line, path.name
    assert "0.2.1 approved by John (Nov 18, 2026)" in STREAM.read_text(encoding="utf-8")
    assert _load(STREAM)["version"] == "0.2.1"
    assert _load(TABLE)["version"] == "0.1.0"


def test_the_message_has_the_contract_fields_and_an_elements_object():
    table = _load(STREAM)["schema"][0]

    assert [(p["name"], p["logicalType"]) for p in table["properties"]] == [
        ("norad_cat_id", "integer"),
        ("epoch_utc", "timestamp"),
        ("fetched_at_utc", "timestamp"),
        ("elements", "object"),
    ]


def test_the_elements_are_the_celestrak_columns_that_are_not_the_key_or_the_pull_facts():
    gp = contract_columns(CONTRACTS / "celestrak_gp.yaml", "celestrak_gp")
    expected = [(c.name, c.logical_type) for c in gp if c.name not in NOT_ELEMENTS]
    elements = next(p for p in _load(STREAM)["schema"][0]["properties"] if p["name"] == "elements")

    assert [(p["name"], p["logicalType"]) for p in elements["properties"]] == expected


def test_the_stream_contract_names_the_topic_retention_watermark_and_checkpoint_path():
    settings = _server_settings(_load(STREAM))

    assert settings["topic"] == "orbit-element-sets"
    assert settings["retention"] == "7 days"
    assert settings["watermark"] == "2 hours"
    assert settings["checkpointLocation"] == (
        "s3a://<lake bucket>/checkpoints/orbit-element-sets/<env>/v2/"
    )
    assert settings["statePartitions"] == "1"


def test_the_message_key_is_the_catalog_number_as_text():
    table = _load(STREAM)["schema"][0]
    properties = {item["property"]: item["value"] for item in table["customProperties"]}

    assert properties["messageKey"] == "norad_cat_id as a string"


def test_the_changed_satellite_table_has_the_columns_the_job_writes():
    columns = contract_columns(TABLE, "orbit_changed_satellite")

    assert [(c.name, c.logical_type, c.required) for c in columns] == [
        ("norad_cat_id", "integer", True),
        ("epoch_utc", "timestamp", True),
        ("previous_epoch_utc", "timestamp", False),
        ("fetched_at_utc", "timestamp", True),
        ("detected_at_utc", "timestamp", True),
    ]


def test_a_changed_satellite_row_is_unique_by_catalog_number_and_epoch():
    properties = _load(TABLE)["schema"][0]["properties"]
    keys = {p["name"]: p["primaryKeyPosition"] for p in properties if p.get("primaryKey")}

    assert keys == {"norad_cat_id": 1, "epoch_utc": 2}
