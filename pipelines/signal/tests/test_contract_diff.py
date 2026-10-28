"""Tests for the contract diff (C8), which checks a source's fields against its contract before
anything is loaded.

A contract lists the lake columns. A column filled straight from the source names the source
field in its `upstreamField` custom property, and may give the source's own type in
`upstreamType`. Columns the loader adds, such as the source URL, have neither and are not part
of the source's schema.
"""

import pytest
from contract_diff import (
    BreakingSchemaChange,
    SchemaDiff,
    assert_no_breaking_change,
    diff_schema,
    load_contract,
    observed_schema_from_records,
)

CONTRACT = """\
apiVersion: v3.0.2
kind: DataContract
name: sample_source
schema:
  - name: sample_table
    properties:
      - name: object_id
        logicalType: integer
        customProperties:
          - property: upstreamField
            value: OBJECT_ID
          - property: upstreamType
            value: integer
      - name: object_name
        logicalType: string
        customProperties:
          - property: upstreamField
            value: OBJECT_NAME
      - name: epoch_utc
        logicalType: timestamp
        customProperties:
          - property: upstreamField
            value: EPOCH
          - property: upstreamType
            value: string
      - name: source_url
        logicalType: string
        description: Added by the loader, not read from the source.
"""


@pytest.fixture
def contract_path(tmp_path):
    path = tmp_path / "sample_source.yaml"
    path.write_text(CONTRACT, encoding="utf-8", newline="\n")
    return path


def test_load_contract_lists_only_the_fields_read_from_the_source(contract_path):
    assert load_contract(contract_path) == {
        "OBJECT_ID": "integer",
        "OBJECT_NAME": None,
        "EPOCH": "string",
    }


def test_load_contract_refuses_a_contract_with_no_source_fields(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("schema:\n  - name: t\n    properties:\n      - name: a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no upstreamField"):
        load_contract(path)


def test_matching_schema_gives_an_empty_diff(contract_path):
    observed = {"OBJECT_ID": "integer", "OBJECT_NAME": "string", "EPOCH": "string"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff == SchemaDiff(added=(), removed=(), changed=())
    assert diff.is_breaking is False


def test_added_field_is_listed_and_is_not_breaking(contract_path):
    observed = {"OBJECT_ID": "integer", "OBJECT_NAME": "string", "EPOCH": "string", "NEW": "number"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff.added == ("NEW",)
    assert diff.is_breaking is False


def test_removed_field_is_breaking(contract_path):
    observed = {"OBJECT_ID": "integer", "EPOCH": "string"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff.removed == ("OBJECT_NAME",)
    assert diff.is_breaking is True


def test_renamed_field_shows_as_removed_and_added(contract_path):
    observed = {"OBJECT_ID": "integer", "SATNAME": "string", "EPOCH": "string"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff.removed == ("OBJECT_NAME",)
    assert diff.added == ("SATNAME",)
    assert diff.is_breaking is True


def test_changed_type_is_breaking_when_the_contract_states_the_type(contract_path):
    observed = {"OBJECT_ID": "string", "OBJECT_NAME": "string", "EPOCH": "string"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff.changed == (("OBJECT_ID", "integer", "string"),)
    assert diff.is_breaking is True


def test_type_is_not_compared_when_the_contract_states_none(contract_path):
    observed = {"OBJECT_ID": "integer", "OBJECT_NAME": "integer", "EPOCH": "string"}
    assert diff_schema(load_contract(contract_path), observed).changed == ()


def test_assert_no_breaking_change_passes_an_added_field():
    assert_no_breaking_change(SchemaDiff(added=("NEW",), removed=(), changed=()), "sample")


def test_assert_no_breaking_change_names_every_breaking_field():
    diff = SchemaDiff(
        added=("SATNAME",), removed=("OBJECT_NAME",), changed=(("A", "integer", "string"),)
    )
    with pytest.raises(BreakingSchemaChange) as raised:
        assert_no_breaking_change(diff, "sample")
    message = str(raised.value)
    assert message.startswith("sample: the source no longer matches its contract")
    assert "removed OBJECT_NAME" in message
    assert "A changed from integer to string" in message
    assert "added SATNAME" in message


def test_observed_schema_takes_each_field_type_from_the_records():
    records = [
        {"OBJECT_ID": 1, "OBJECT_NAME": "STARLINK-1 [DTC]", "INCLINATION": 53.0, "FLAG": True},
        {"OBJECT_ID": 2, "OBJECT_NAME": "STARLINK-2", "INCLINATION": 43.0, "FLAG": False},
    ]
    assert observed_schema_from_records(records) == {
        "OBJECT_ID": "integer",
        "OBJECT_NAME": "string",
        "INCLINATION": "number",
        "FLAG": "boolean",
    }


def test_observed_schema_unions_fields_and_skips_nulls():
    records = [{"A": None, "B": 1}, {"A": "x"}]
    assert observed_schema_from_records(records) == {"A": "string", "B": "integer"}


def test_field_that_is_always_null_is_present_with_type_null():
    assert observed_schema_from_records([{"A": None}, {"A": None}]) == {"A": "null"}


def test_always_null_field_is_neither_removed_nor_changed(contract_path):
    observed = {"OBJECT_ID": "null", "OBJECT_NAME": "string", "EPOCH": "string"}
    diff = diff_schema(load_contract(contract_path), observed)
    assert diff == SchemaDiff(added=(), removed=(), changed=())


def test_observed_schema_widens_integer_and_number_to_number():
    assert observed_schema_from_records([{"A": 1}, {"A": 1.5}]) == {"A": "number"}


def test_observed_schema_reports_a_field_with_two_types_as_mixed():
    assert observed_schema_from_records([{"A": 1}, {"A": "1"}]) == {"A": "mixed"}


def test_observed_schema_refuses_no_records():
    with pytest.raises(ValueError, match="no records"):
        observed_schema_from_records([])
