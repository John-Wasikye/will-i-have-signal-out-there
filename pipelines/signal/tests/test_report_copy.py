"""Tests for the nightly report copy (C23): read from DynamoDB, set aside, mark, count.

ADR 0012: the copy reads reports not yet copied, and only after the lake write marks each one
copied and sets it to expire 30 days later. FR-56 set-aside rules, as decided by John on
Nov 9, 2026: a report more than 10 km from every Phase A trail point is outside the mapped area;
a cell and hour with 3 or more reports that hold both answers is a contradicting burst.
No test calls AWS.
"""

from datetime import UTC, date, datetime

import h3
import pytest
from report_copy import (
    CONTRADICTING_BURST,
    OUTSIDE_MAPPED_AREA,
    CopiedReport,
    cell_day_rows,
    copy_marker,
    mark_copied,
    read_reports_to_copy,
    report_rows,
    set_aside_reasons,
    set_aside_rows,
)

RUN_TIME = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
MARKER = "2026-11-10T10:00:00Z"
TRAIL_POINTS = [(36.0579, -112.143), (36.10, -112.10)]
NEAR = h3.latlng_to_cell(36.0580, -112.1431, 9)
FAR = h3.latlng_to_cell(36.0579, -111.90, 9)  # about 22 km east of the nearest point
HOUR = datetime(2026, 11, 9, 18, tzinfo=UTC)


def _report(report_id: str, cell: str = NEAR, had_signal: bool = True, hour=HOUR) -> CopiedReport:
    return CopiedReport(report_id, cell, "T-Mobile", had_signal, hour)


def _item(report_id: str, **extra) -> dict:
    item = {
        "report_id": {"S": report_id},
        "h3_cell_res9": {"S": NEAR},
        "carrier": {"S": "T-Mobile"},
        "had_signal": {"BOOL": True},
        "report_hour_utc": {"S": "2026-11-09T18:00:00Z"},
    }
    return item | extra


class ClientError(Exception):
    """Shaped like botocore's ClientError, which the tests do not import."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeDynamoDB:
    """Answers scans one page at a time, and records every update."""

    def __init__(self, pages: list[list[dict]], refuse: set[str] = frozenset()) -> None:
        self.pages = pages
        self.refuse = refuse
        self.scans: list[dict] = []
        self.updates: list[dict] = []

    def scan(self, **request) -> dict:
        self.scans.append(request)
        index = int(request.get("ExclusiveStartKey", {}).get("page", {"N": "0"})["N"])
        answer = {"Items": self.pages[index]}
        if index + 1 < len(self.pages):
            answer["LastEvaluatedKey"] = {"page": {"N": str(index + 1)}}
        return answer

    def update_item(self, **request) -> dict:
        self.updates.append(request)
        if request["Key"]["report_id"]["S"] in self.refuse:
            raise ClientError("ConditionalCheckFailedException")
        return {}


# --- Reading and marking -------------------------------------------------------------------


def test_the_copy_marker_is_the_run_time_in_utc():
    assert copy_marker(RUN_TIME) == MARKER


def test_reports_not_yet_copied_are_read_across_every_page():
    client = FakeDynamoDB([[_item("a")], [_item("b")]])

    reports = read_reports_to_copy(client, "reports-table", MARKER)

    assert [report.report_id for report in reports] == ["a", "b"]
    assert reports[0] == CopiedReport("a", NEAR, "T-Mobile", True, HOUR)
    assert len(client.scans) == 2
    assert client.scans[0]["TableName"] == "reports-table"
    assert client.scans[0]["ConsistentRead"] is True


def test_the_read_takes_new_reports_and_the_ones_this_run_already_copied():
    """A rerun of the same night must find the reports it marked, or it would empty its copy."""
    client = FakeDynamoDB([[]])

    read_reports_to_copy(client, "reports-table", MARKER)

    scan = client.scans[0]
    assert "attribute_not_exists(copied_at_utc)" in scan["FilterExpression"]
    assert {"S": MARKER} in scan["ExpressionAttributeValues"].values()


def test_marking_sets_the_copy_time_and_the_expiry_without_creating_rows():
    client = FakeDynamoDB([[]])

    marked = mark_copied(client, "reports-table", ["a", "b"], MARKER, 1_765_360_800)

    assert marked == 2
    first = client.updates[0]
    assert first["TableName"] == "reports-table"
    assert first["Key"] == {"report_id": {"S": "a"}}
    assert "copied_at_utc" in first["UpdateExpression"]
    assert "expires_at_epoch" in first["UpdateExpression"]
    assert "attribute_exists(report_id)" in first["ConditionExpression"]
    assert {"N": "1765360800"} in first["ExpressionAttributeValues"].values()
    assert {"S": MARKER} in first["ExpressionAttributeValues"].values()


def test_a_report_gone_or_copied_by_another_run_is_skipped_not_fatal():
    client = FakeDynamoDB([[]], refuse={"b"})

    assert mark_copied(client, "reports-table", ["a", "b", "c"], MARKER, 1) == 2


def test_any_other_marking_error_stops_the_copy():
    class Broken(FakeDynamoDB):
        def update_item(self, **request):
            raise ClientError("ProvisionedThroughputExceededException")

    with pytest.raises(ClientError):
        mark_copied(Broken([[]]), "reports-table", ["a"], MARKER, 1)


# --- Set-aside rules (FR-56) ---------------------------------------------------------------


def test_a_report_more_than_10_km_from_every_trail_point_is_set_aside():
    reasons = set_aside_reasons([_report("near"), _report("far", FAR)], TRAIL_POINTS)

    assert reasons == {"far": OUTSIDE_MAPPED_AREA}


def test_a_cell_hour_with_3_reports_and_both_answers_is_set_aside_whole():
    reports = [_report("a"), _report("b"), _report("c", had_signal=False)]

    assert set_aside_reasons(reports, TRAIL_POINTS) == dict.fromkeys("abc", CONTRADICTING_BURST)


def test_agreeing_reports_or_only_two_disagreeing_ones_are_kept():
    agreeing = [_report("a"), _report("b"), _report("c")]
    other_hour = datetime(2026, 11, 9, 20, tzinfo=UTC)
    two = [_report("d", hour=other_hour), _report("e", had_signal=False, hour=other_hour)]

    assert set_aside_reasons(agreeing + two, TRAIL_POINTS) == {}


def test_reports_in_different_hours_do_not_make_a_burst():
    later = datetime(2026, 11, 9, 19, tzinfo=UTC)
    reports = [_report("a"), _report("b"), _report("c", had_signal=False, hour=later)]

    assert set_aside_reasons(reports, TRAIL_POINTS) == {}


def test_outside_the_mapped_area_wins_over_a_burst():
    reports = [_report(x, FAR, had_signal=x != "c") for x in "abc"]

    assert set(set_aside_reasons(reports, TRAIL_POINTS).values()) == {OUTSIDE_MAPPED_AREA}


def test_set_aside_needs_trail_points():
    with pytest.raises(ValueError, match="trail point"):
        set_aside_reasons([_report("a")], [])


# --- Lake rows -----------------------------------------------------------------------------


def test_report_rows_match_the_signal_report_contract():
    rows = report_rows([_report("a")], RUN_TIME)

    assert rows == [
        {
            "report_id": "a",
            "h3_cell_res9": NEAR,
            "carrier": "T-Mobile",
            "had_signal": True,
            "report_hour_utc": HOUR,
            "copied_at_utc": RUN_TIME,
        }
    ]


def test_set_aside_rows_carry_the_reason():
    rows = set_aside_rows([_report("a"), _report("b")], {"b": CONTRADICTING_BURST})

    assert rows == [
        {
            "report_id": "b",
            "h3_cell_res9": NEAR,
            "carrier": "T-Mobile",
            "had_signal": True,
            "report_hour_utc": HOUR,
            "reason": CONTRADICTING_BURST,
        }
    ]


def test_cell_day_rows_count_reports_per_cell_and_utc_day():
    rows = [
        {"h3_cell_res9": NEAR, "had_signal": True, "report_hour_utc": HOUR},
        {"h3_cell_res9": NEAR, "had_signal": False, "report_hour_utc": HOUR},
        {
            "h3_cell_res9": NEAR,
            "had_signal": True,
            "report_hour_utc": datetime(2026, 11, 8, 23, tzinfo=UTC),
        },
        {"h3_cell_res9": FAR, "had_signal": True, "report_hour_utc": HOUR},
    ]

    counted = cell_day_rows(rows, RUN_TIME, date(2026, 11, 1))

    assert sorted(counted, key=lambda r: (r["h3_cell_res9"], r["report_date_utc"])) == sorted(
        [
            {
                "h3_cell_res9": NEAR,
                "report_date_utc": date(2026, 11, 9),
                "report_count": 2,
                "signal_yes_count": 1,
                "signal_no_count": 1,
                "built_at_utc": RUN_TIME,
            },
            {
                "h3_cell_res9": NEAR,
                "report_date_utc": date(2026, 11, 8),
                "report_count": 1,
                "signal_yes_count": 1,
                "signal_no_count": 0,
                "built_at_utc": RUN_TIME,
            },
            {
                "h3_cell_res9": FAR,
                "report_date_utc": date(2026, 11, 9),
                "report_count": 1,
                "signal_yes_count": 1,
                "signal_no_count": 0,
                "built_at_utc": RUN_TIME,
            },
        ],
        key=lambda r: (r["h3_cell_res9"], r["report_date_utc"]),
    )


def test_cell_day_rows_leave_out_days_before_the_recount_window():
    rows = [{"h3_cell_res9": NEAR, "had_signal": True, "report_hour_utc": HOUR}]

    assert cell_day_rows(rows, RUN_TIME, date(2026, 11, 10)) == []
