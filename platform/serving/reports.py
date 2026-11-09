"""Report API (C22): POST /reports takes one hiker signal report and applies the limits.

API Gateway sends POST /reports here, to its own small function, apart from the read-only API.
The rules:

- Limits (ADR 0011): 10 reports a UTC day per visitor, one per place (H3 cell) per visitor
  every 24 hours, and 50 a UTC day for the whole system. Each is counted by the hour the
  report was made on the phone, not by when it arrives, so a batch sent after being offline
  is judged by its own hours.
- Window (ADR 0026): a report hour may be up to 48 hours before arrival and up to 1 hour after.
- Privacy (ADR 0025): the visitor ID is used only as a keyed hash (HMAC-SHA256) in the
  counters table, and the report itself holds no ID. The place is hashed into the counter key
  too, so the counters hold no location. Nothing from the request is logged.
- Counters expire 72 hours after the end of their UTC day (ADR 0026).

The report and every counter change go in one DynamoDB transaction: a refused report changes
nothing. The one-per-place rule needs the hours already reported there, so the function reads
them first and writes back with a version check; a parallel request for the same place makes
the write fail, and the function reads again.

This file imports only the standard library at load time, so a cold start stays quick.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

VISITOR_DAILY_LIMIT = 10
SYSTEM_DAILY_LIMIT = 50
CELL_GAP = timedelta(hours=24)
MAX_REPORT_AGE = timedelta(hours=48)
MAX_CLOCK_AHEAD = timedelta(hours=1)
COUNTER_LIFETIME_AFTER_DAY = timedelta(hours=72)
MAX_BODY_BYTES = 1024
CELL_ATTEMPTS = 3

# The carriers a hiker can choose. OQ-11 makes the list every carrier in the park's FCC files;
# these are the three national networks until C13 loads those files.
CARRIERS = frozenset({"AT&T", "T-Mobile", "Verizon"})

REPORT_FIELDS = frozenset({"cell", "carrier", "had_signal", "report_hour_utc"})
_VISITOR_ID = re.compile(r"[0-9a-f]{32}")
_CELL_TEXT = re.compile(r"[0-9a-f]{15}")
_REPORT_HOUR = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00(Z|\+00:00)")

logger = logging.getLogger(__name__)


class Limit(StrEnum):
    """The limit that refused a report."""

    VISITOR_DAY = "visitor_day"
    CELL = "cell"
    SYSTEM_DAY = "system_day"


LIMIT_MESSAGES = {
    Limit.VISITOR_DAY: "You have sent 10 reports for this day (UTC). Please try again tomorrow.",
    Limit.CELL: "You already reported this same place within 24 hours.",
    Limit.SYSTEM_DAY: "The site has taken all the reports it can for today (UTC).",
}
UNAVAILABLE_MESSAGE = "Reports cannot be saved right now. Please try again later."


class InvalidRequest(Exception):
    """The request breaks the schema or the report-hour window."""


class LimitReached(Exception):
    """A report limit refused the report."""

    def __init__(self, limit: Limit) -> None:
        """Keep which limit refused the report."""
        super().__init__(limit.value)
        self.limit = limit


class VersionConflict(Exception):
    """Another request changed the same place's counter between the read and the write."""


class StoreUnavailable(Exception):
    """DynamoDB or the key in Parameter Store cannot be reached."""


@dataclass(frozen=True)
class Report:
    """A report that passed the schema checks."""

    cell: str
    carrier: str
    had_signal: bool
    report_hour: datetime


@dataclass(frozen=True)
class CellState:
    """The hours (epoch seconds) a visitor already reported at one place, and its version."""

    hours: tuple[int, ...]
    version: int | None


@dataclass(frozen=True)
class Commit:
    """Everything one accepted report writes, in one transaction."""

    report_item: dict
    visitor_day_key: str
    system_day_key: str
    cell_key: str
    cell_hours: tuple[int, ...]
    cell_version: int | None
    counter_expires_at_epoch: int
    cell_expires_at_epoch: int


# --- Reading the request -------------------------------------------------------------------


def is_resolution_9_cell(text: str) -> bool:
    """Return True for an H3 cell index at resolution 9, checked from its bits.

    The function has no H3 library. An index is a cell (mode 1) with a resolution field and
    one 3-bit digit per resolution: digits up to 9 run 0 to 6, and the unused ones are all 7.
    """
    if not _CELL_TEXT.fullmatch(text):
        return False
    value = int(text, 16)
    mode = (value >> 59) & 0xF
    resolution = (value >> 52) & 0xF
    base_cell = (value >> 45) & 0x7F
    if value >> 63 or mode != 1 or resolution != 9 or base_cell > 121:
        return False
    digits = [(value >> (3 * (15 - level))) & 0x7 for level in range(1, 16)]
    return all(digit < 7 for digit in digits[:9]) and all(digit == 7 for digit in digits[9:])


def parse_visitor_id(headers: dict) -> str:
    """Return the visitor ID from the X-Visitor-Id header: 32 lowercase hexadecimal characters."""
    visitor_id = {name.lower(): value for name, value in headers.items()}.get("x-visitor-id")
    if not isinstance(visitor_id, str) or not _VISITOR_ID.fullmatch(visitor_id):
        raise InvalidRequest("The X-Visitor-Id header must be 32 lowercase hexadecimal characters.")
    return visitor_id


def read_body(event: dict) -> str:
    """Return the request body as text, decoding base64 when API Gateway used it."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise InvalidRequest("The body is not valid JSON.") from error
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise InvalidRequest("The body is too long.")
    return raw


def parse_report(body: str) -> Report:
    """Check the body against the ReportIn schema and return the report."""
    try:
        data = json.loads(body)
    except ValueError as error:
        raise InvalidRequest("The body is not valid JSON.") from error
    if not isinstance(data, dict) or set(data) != REPORT_FIELDS:
        raise InvalidRequest(
            "The body must have exactly: cell, carrier, had_signal, report_hour_utc."
        )
    if not isinstance(data["cell"], str) or not is_resolution_9_cell(data["cell"]):
        raise InvalidRequest("cell must be an H3 resolution 9 cell.")
    if data["carrier"] not in CARRIERS:
        raise InvalidRequest("carrier must be one of: " + ", ".join(sorted(CARRIERS)) + ".")
    if not isinstance(data["had_signal"], bool):
        raise InvalidRequest("had_signal must be true or false.")
    hour_text = data["report_hour_utc"]
    if not isinstance(hour_text, str) or not _REPORT_HOUR.fullmatch(hour_text):
        raise InvalidRequest(
            "report_hour_utc must be a UTC time on the hour, like 2026-11-09T18:00:00Z."
        )
    try:
        hour = datetime.fromisoformat(hour_text.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidRequest("report_hour_utc is not a real date and time.") from error
    return Report(data["cell"], data["carrier"], data["had_signal"], hour.astimezone(UTC))


def check_report_hour(hour: datetime, now: datetime) -> None:
    """Refuse a report hour more than 48 hours before arrival or more than 1 hour after it."""
    if hour < now - MAX_REPORT_AGE or hour > now + MAX_CLOCK_AHEAD:
        raise InvalidRequest("report_hour_utc must be within the last 48 hours.")


# --- Limits --------------------------------------------------------------------------------


def visitor_hash(secret: bytes, visitor_id: str) -> str:
    """Return the keyed hash that stands for the visitor in the counters table (ADR 0025)."""
    return hmac.new(secret, visitor_id.encode("ascii"), hashlib.sha256).hexdigest()


def cell_key(secret: bytes, visitor_id: str, cell: str) -> str:
    """Return the counter key for one visitor at one place. It reveals neither."""
    digest = hmac.new(secret, f"{visitor_id}:{cell}".encode("ascii"), hashlib.sha256).hexdigest()
    return f"cell#{digest}"


def counter_expiry_epoch(day_start_epoch: int) -> int:
    """Return the expiry of a counter for the UTC day that starts at ``day_start_epoch``."""
    day_end = day_start_epoch + int(timedelta(days=1).total_seconds())
    return day_end + int(COUNTER_LIFETIME_AFTER_DAY.total_seconds())


def _day_start_epoch(moment: datetime) -> int:
    return int(datetime(moment.year, moment.month, moment.day, tzinfo=UTC).timestamp())


def too_close(hours: tuple[int, ...], hour: int) -> bool:
    """Return True when the visitor already reported this place within 24 hours of ``hour``."""
    gap = int(CELL_GAP.total_seconds())
    return any(abs(existing - hour) < gap for existing in hours)


def build_commit(
    secret: bytes,
    visitor_id: str,
    report: Report,
    report_id: str,
    state: CellState,
    key: str,
    now: datetime,
) -> Commit:
    """Build the writes for one accepted report.

    The place's list keeps only hours that can still clash: a new report is at most 48 hours
    old, so an hour older than 72 hours before now never can.
    """
    hour = int(report.report_hour.timestamp())
    oldest_useful = int((now - MAX_REPORT_AGE - CELL_GAP).timestamp())
    hours = tuple(sorted({h for h in state.hours if h > oldest_useful} | {hour}))
    day = report.report_hour.strftime("%Y-%m-%d")
    latest = datetime.fromtimestamp(hours[-1], tz=UTC)
    return Commit(
        report_item={
            "report_id": report_id,
            "h3_cell_res9": report.cell,
            "carrier": report.carrier,
            "had_signal": report.had_signal,
            "report_hour_utc": report.report_hour.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        visitor_day_key=f"visitor#{visitor_hash(secret, visitor_id)}#{day}",
        system_day_key=f"system#{day}",
        cell_key=key,
        cell_hours=hours,
        cell_version=state.version,
        counter_expires_at_epoch=counter_expiry_epoch(_day_start_epoch(report.report_hour)),
        cell_expires_at_epoch=counter_expiry_epoch(_day_start_epoch(latest)),
    )


def submit_report(
    store,
    secret: bytes,
    visitor_id: str,
    report: Report,
    now: datetime,
    new_report_id: Callable[[], str],
) -> None:
    """Apply the limits and store the report, or raise why it was refused."""
    check_report_hour(report.report_hour, now)
    key = cell_key(secret, visitor_id, report.cell)
    for _ in range(CELL_ATTEMPTS):
        state = store.read_cell(key)
        if too_close(state.hours, int(report.report_hour.timestamp())):
            raise LimitReached(Limit.CELL)
        try:
            store.commit(build_commit(secret, visitor_id, report, new_report_id(), state, key, now))
            return
        except VersionConflict:
            continue
    raise StoreUnavailable("The place's counter kept changing.")


# --- Answers -------------------------------------------------------------------------------


def _answer(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _error(status: int, code: str, message: str) -> dict:
    return _answer(status, {"error": {"code": code, "message": message}})


def handle(
    event: dict,
    store,
    load_secret: Callable[[], bytes],
    now: datetime,
    new_report_id: Callable[[], str],
) -> dict:
    """Answer one POST /reports request. Messages never repeat what the request sent."""
    try:
        visitor_id = parse_visitor_id(event.get("headers") or {})
        report = parse_report(read_body(event))
        submit_report(store, load_secret(), visitor_id, report, now, new_report_id)
    except InvalidRequest as error:
        return _error(400, "invalid_request", str(error))
    except LimitReached as refused:
        return _error(429, "report_limit_exceeded", LIMIT_MESSAGES[refused.limit])
    except StoreUnavailable as error:
        logger.warning("Report store unavailable: %s", type(error.__cause__ or error).__name__)
        return _error(503, "dependency_unavailable", UNAVAILABLE_MESSAGE)
    return _answer(202, {"status": "accepted"})


# --- DynamoDB ------------------------------------------------------------------------------


class DynamoReportStore:
    """Reads and writes the reports and counters tables with the low-level boto3 client."""

    def __init__(self, client, reports_table: str, counters_table: str) -> None:
        """Use ``client`` (boto3 DynamoDB) on the two named tables."""
        self._client = client
        self._reports = reports_table
        self._counters = counters_table

    def read_cell(self, key: str) -> CellState:
        """Return the hours and version stored for one visitor at one place."""
        try:
            answer = self._client.get_item(
                TableName=self._counters, Key={"counter_key": {"S": key}}, ConsistentRead=True
            )
        except Exception as error:  # noqa: BLE001, any client failure means the store is down
            raise StoreUnavailable(type(error).__name__) from error
        item = answer.get("Item")
        if item is None:
            return CellState(hours=(), version=None)
        hours = tuple(int(value["N"]) for value in item["report_hours"]["L"])
        return CellState(hours=hours, version=int(item["version"]["N"]))

    def commit(self, commit: Commit) -> None:
        """Write the report and the three counters together, or raise why they were refused."""
        try:
            self._client.transact_write_items(TransactItems=self._transaction(commit))
        except Exception as error:  # noqa: BLE001, mapped below, anything else is the store
            raise self._refusal(error) from error

    def _transaction(self, commit: Commit) -> list[dict]:
        report = commit.report_item
        expires = {"N": str(commit.counter_expires_at_epoch)}
        cell_condition = (
            "attribute_not_exists(counter_key)"
            if commit.cell_version is None
            else "version = :expected"
        )
        cell_put = {
            "TableName": self._counters,
            "Item": {
                "counter_key": {"S": commit.cell_key},
                "report_hours": {"L": [{"N": str(hour)} for hour in commit.cell_hours]},
                "version": {"N": str((commit.cell_version or 0) + 1)},
                "expires_at_epoch": {"N": str(commit.cell_expires_at_epoch)},
            },
            "ConditionExpression": cell_condition,
        }
        if commit.cell_version is not None:
            cell_put["ExpressionAttributeValues"] = {":expected": {"N": str(commit.cell_version)}}
        return [
            {
                "Put": {
                    "TableName": self._reports,
                    "Item": {
                        "report_id": {"S": report["report_id"]},
                        "h3_cell_res9": {"S": report["h3_cell_res9"]},
                        "carrier": {"S": report["carrier"]},
                        "had_signal": {"BOOL": report["had_signal"]},
                        "report_hour_utc": {"S": report["report_hour_utc"]},
                    },
                    "ConditionExpression": "attribute_not_exists(report_id)",
                }
            },
            {"Update": self._count_up(commit.visitor_day_key, VISITOR_DAILY_LIMIT, expires)},
            {"Update": self._count_up(commit.system_day_key, SYSTEM_DAILY_LIMIT, expires)},
            {"Put": cell_put},
        ]

    def _count_up(self, key: str, limit: int, expires: dict) -> dict:
        return {
            "TableName": self._counters,
            "Key": {"counter_key": {"S": key}},
            "UpdateExpression": "ADD #count :one SET expires_at_epoch = :expires",
            "ConditionExpression": "attribute_not_exists(counter_key) OR #count < :limit",
            "ExpressionAttributeNames": {"#count": "count"},
            "ExpressionAttributeValues": {
                ":one": {"N": "1"},
                ":limit": {"N": str(limit)},
                ":expires": expires,
            },
        }

    @staticmethod
    def _refusal(error: Exception) -> Exception:
        """Turn a client error into the refusal it stands for."""
        response = getattr(error, "response", None) or {}
        reasons = [reason.get("Code") for reason in response.get("CancellationReasons", [])]
        if len(reasons) == 4:
            checks = {1: LimitReached(Limit.VISITOR_DAY), 2: LimitReached(Limit.SYSTEM_DAY)}
            for index, refusal in checks.items():
                if reasons[index] == "ConditionalCheckFailed":
                    return refusal
            if reasons[3] in {"ConditionalCheckFailed", "TransactionConflict"}:
                return VersionConflict()
        return StoreUnavailable(type(error).__name__)


# --- Lambda entry point --------------------------------------------------------------------

_store: DynamoReportStore | None = None
_secret: bytes | None = None


def _load_secret() -> bytes:
    """Read the HMAC key from Parameter Store once per running copy of the function."""
    global _secret
    if _secret is None:
        import boto3  # The Lambda runtime provides boto3, so it is not in the package.

        try:
            answer = boto3.client("ssm").get_parameter(
                Name=os.environ["VISITOR_KEY_PARAMETER"], WithDecryption=True
            )
        except Exception as error:  # noqa: BLE001, a missing key means reports cannot be taken
            raise StoreUnavailable(type(error).__name__) from error
        _secret = answer["Parameter"]["Value"].encode("utf-8")
    return _secret


def _dynamo_store() -> DynamoReportStore:
    global _store
    if _store is None:
        import boto3

        _store = DynamoReportStore(
            boto3.client("dynamodb"), os.environ["REPORTS_TABLE"], os.environ["COUNTERS_TABLE"]
        )
    return _store


def handler(event: dict, context: object) -> dict:
    """Lambda entry point for POST /reports."""
    try:
        store = _dynamo_store()
    except Exception as error:  # noqa: BLE001, log the kind of failure only, never the request
        logger.warning("Report store could not start: %s", type(error).__name__)
        return _error(503, "dependency_unavailable", UNAVAILABLE_MESSAGE)
    return handle(
        event,
        store=store,
        load_secret=_load_secret,
        now=datetime.now(UTC),
        new_report_id=lambda: uuid.uuid4().hex,
    )
