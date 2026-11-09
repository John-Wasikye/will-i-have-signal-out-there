"""Nightly report copy (C23): read hiker reports from DynamoDB, set aside, mark, and count.

The report API writes each report to DynamoDB with no expiry. The nightly copy (ADR 0012):

1. reads the reports not yet copied, plus any this same run already marked, so a rerun of the
   night rewrites the same copy instead of an empty one;
2. sets aside reports a rule flags (FR-56), so they reach neither the counts nor the labels;
3. after the lake write, marks each report copied and sets it to expire 30 days later. A copy
   that fails before this step leaves every report unmarked, so none is lost.

Set-aside rules, decided by John on Nov 9, 2026:
- outside the mapped area: the report's cell centre is more than 10 km from every Phase A
  trail point;
- contradicting burst: one cell and one hour with 3 or more reports that hold both answers. The
  rule sees one night's copy; reports of the same hour copied on another night are not compared.

``cell_day_rows`` counts the kept reports per cell and UTC day for ``report_cell_day``, which keeps
counts after the reports are deleted (ADR 0034). This module does no Spark; signal_nightly.py
writes the rows.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import h3

OUTSIDE_MAPPED_AREA = "outside_mapped_area"
CONTRADICTING_BURST = "contradicting_burst"
MAPPED_DISTANCE_M = 10_000
BURST_MIN_REPORTS = 3
EARTH_RADIUS_M = 6_371_008.8
_REPORT_FIELDS = ("report_id", "h3_cell_res9", "carrier", "had_signal", "report_hour_utc")


@dataclass(frozen=True)
class CopiedReport:
    """One report as the report API stored it. It holds no visitor ID."""

    report_id: str
    h3_cell_res9: str
    carrier: str
    had_signal: bool
    report_hour_utc: datetime


def copy_marker(run_time: datetime) -> str:
    """Return the run's time as stored on each report it copies, like 2026-11-10T10:00:00Z."""
    return run_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_hour(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _from_item(item: dict) -> CopiedReport:
    return CopiedReport(
        report_id=item["report_id"]["S"],
        h3_cell_res9=item["h3_cell_res9"]["S"],
        carrier=item["carrier"]["S"],
        had_signal=item["had_signal"]["BOOL"],
        report_hour_utc=_parse_hour(item["report_hour_utc"]["S"]),
    )


def read_reports_to_copy(client, table: str, marker: str) -> list[CopiedReport]:  # noqa: ANN001
    """Return every report not yet copied, or copied by the run with this ``marker``.

    The table holds at most 30 days of reports at 50 a day, so a scan of it is small.
    """
    request = {
        "TableName": table,
        "ConsistentRead": True,
        "ProjectionExpression": ", ".join(_REPORT_FIELDS),
        "FilterExpression": "attribute_not_exists(copied_at_utc) OR copied_at_utc = :marker",
        "ExpressionAttributeValues": {":marker": {"S": marker}},
    }
    reports = []
    while True:
        answer = client.scan(**request)
        reports.extend(_from_item(item) for item in answer.get("Items", []))
        if "LastEvaluatedKey" not in answer:
            return reports
        request["ExclusiveStartKey"] = answer["LastEvaluatedKey"]


def mark_copied(
    client,  # noqa: ANN001, a boto3 DynamoDB client
    table: str,
    report_ids: Iterable[str],
    marker: str,
    expires_at_epoch: int,
) -> int:
    """Mark each report copied and set its expiry. Return how many were marked.

    The condition stops an update from creating a row for a report that expired meanwhile, and
    from moving a report another run copied. Such a report is skipped.
    """
    marked = 0
    for report_id in report_ids:
        try:
            client.update_item(
                TableName=table,
                Key={"report_id": {"S": report_id}},
                UpdateExpression="SET copied_at_utc = :marker, expires_at_epoch = :expires",
                ConditionExpression=(
                    "attribute_exists(report_id) AND "
                    "(attribute_not_exists(copied_at_utc) OR copied_at_utc = :marker)"
                ),
                ExpressionAttributeValues={
                    ":marker": {"S": marker},
                    ":expires": {"N": str(expires_at_epoch)},
                },
            )
        except Exception as error:
            code = getattr(error, "response", {}).get("Error", {}).get("Code")
            if code != "ConditionalCheckFailedException":
                raise
            continue
        marked += 1
    return marked


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Great-circle distance in meters between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _outside_mapped_area(cell: str, trail_points: Sequence[tuple[float, float]]) -> bool:
    centre = h3.cell_to_latlng(cell)
    return all(_distance_m(centre, point) > MAPPED_DISTANCE_M for point in trail_points)


def set_aside_reasons(
    reports: Sequence[CopiedReport], trail_points: Sequence[tuple[float, float]]
) -> dict[str, str]:
    """Return the reason for each report a rule sets aside, by report ID."""
    if not trail_points:
        raise ValueError("set-aside needs the trail points to know the mapped area")
    reasons = {
        report.report_id: OUTSIDE_MAPPED_AREA
        for report in reports
        if _outside_mapped_area(report.h3_cell_res9, trail_points)
    }
    groups: dict[tuple[str, datetime], list[CopiedReport]] = defaultdict(list)
    for report in reports:
        if report.report_id not in reasons:
            groups[(report.h3_cell_res9, report.report_hour_utc)].append(report)
    for group in groups.values():
        answers = {report.had_signal for report in group}
        if len(group) >= BURST_MIN_REPORTS and answers == {True, False}:
            reasons.update(
                dict.fromkeys((report.report_id for report in group), CONTRADICTING_BURST)
            )
    return reasons


def _base_row(report: CopiedReport) -> dict:
    return {
        "report_id": report.report_id,
        "h3_cell_res9": report.h3_cell_res9,
        "carrier": report.carrier,
        "had_signal": report.had_signal,
        "report_hour_utc": report.report_hour_utc,
    }


def report_rows(reports: Iterable[CopiedReport], copied_at: datetime) -> list[dict]:
    """Rows for ``signal_report``."""
    return [_base_row(report) | {"copied_at_utc": copied_at} for report in reports]


def set_aside_rows(reports: Iterable[CopiedReport], reasons: dict[str, str]) -> list[dict]:
    """Rows for ``signal_report_set_aside``: only the reports a rule flagged."""
    return [
        _base_row(report) | {"reason": reasons[report.report_id]}
        for report in reports
        if report.report_id in reasons
    ]


def cell_day_rows(rows: Iterable[dict], built_at: datetime, first_day: date) -> list[dict]:
    """Count kept reports per cell and UTC day, from ``first_day`` on, for ``report_cell_day``."""
    totals: Counter[tuple[str, date]] = Counter()
    yes: Counter[tuple[str, date]] = Counter()
    for row in rows:
        day = row["report_hour_utc"].astimezone(UTC).date()
        if day < first_day:
            continue
        key = (row["h3_cell_res9"], day)
        totals[key] += 1
        yes[key] += 1 if row["had_signal"] else 0
    return [
        {
            "h3_cell_res9": cell,
            "report_date_utc": day,
            "report_count": count,
            "signal_yes_count": yes[(cell, day)],
            "signal_no_count": count - yes[(cell, day)],
            "built_at_utc": built_at,
        }
        for (cell, day), count in sorted(totals.items())
    ]
