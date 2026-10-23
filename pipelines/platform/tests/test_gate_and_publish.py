"""Publish gate and write-audit-publish tests."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from gate import GateResult, check_not_empty, check_row_limit, evaluate
from publish import PublishRefused, publish_tables


def test_empty_table_fails_the_check():
    assert check_not_empty("t", 0) == "t: no rows"
    assert check_not_empty("t", 1) is None


def test_row_limit_fails_above_the_limit_only():
    assert check_row_limit("t", 10, 10) is None
    assert check_row_limit("t", 11, 10) == "t: 11 rows is over the limit of 10"


def test_evaluate_passes_only_when_no_check_fails():
    assert evaluate([None, None]) == GateResult(passed=True, failures=())
    failed = evaluate([None, "t: no rows"])
    assert failed.passed is False
    assert failed.failures == ("t: no rows",)


def _table(rows: int = 2) -> pa.Table:
    return pa.table({"key": [f"k{i}" for i in range(rows)], "value": list(range(rows))})


def test_publish_writes_every_table_when_the_gate_passes(tmp_path):
    written = publish_tables({"sample_answer": _table()}, GateResult(True), tmp_path)
    assert written == [tmp_path / "sample_answer.parquet"]
    assert pq.read_table(written[0]).num_rows == 2
    assert not (tmp_path / ".staging").exists()


def test_publish_refuses_when_the_gate_failed_and_writes_nothing(tmp_path):
    failed = GateResult(False, ("t: no rows",))
    with pytest.raises(PublishRefused, match="t: no rows"):
        publish_tables({"sample_answer": _table()}, failed, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_publish_keeps_the_old_file_when_a_later_gate_fails(tmp_path):
    publish_tables({"sample_answer": _table(2)}, GateResult(True), tmp_path)
    with pytest.raises(PublishRefused):
        publish_tables({"sample_answer": _table(5)}, GateResult(False, ("bad",)), tmp_path)
    assert pq.read_table(tmp_path / "sample_answer.parquet").num_rows == 2


@pytest.mark.parametrize("name", ["Bad-Name", "1starts_with_digit", "has space", ""])
def test_publish_rejects_table_names_that_are_not_safe(tmp_path, name):
    with pytest.raises(ValueError, match="must be lowercase"):
        publish_tables({name: _table()}, GateResult(True), tmp_path)
