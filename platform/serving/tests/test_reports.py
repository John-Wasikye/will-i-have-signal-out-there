"""Tests for the report API (C22): POST /reports and its limits.

The rules come from ADR 0011 (limits), ADR 0025 (visitor ID kept only as a keyed hash) and
ADR 0026 (UTC day, 48-hour window, counters live 72 hours after their day). The handler is
tested through ``handle`` with an in-memory store that keeps the same promises as DynamoDB:
a commit is all or nothing. The DynamoDB store is tested on the requests it sends.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import h3
import pytest
import reports
from botocore.exceptions import ClientError
from reports import (
    SYSTEM_DAILY_LIMIT,
    VISITOR_DAILY_LIMIT,
    CellState,
    Commit,
    DynamoReportStore,
    Limit,
    LimitReached,
    StoreUnavailable,
    VersionConflict,
)

SECRET = b"fake-test-key-not-a-real-secret"
VISITOR = "0123456789abcdef0123456789abcdef"
OTHER_VISITOR = "fedcba9876543210fedcba9876543210"
NOW = datetime(2026, 11, 9, 18, 20, tzinfo=UTC)
THIS_HOUR = datetime(2026, 11, 9, 18, tzinfo=UTC)
CELL = h3.latlng_to_cell(36.0579, -112.1430, 9)


def _cell_near(index: int) -> str:
    """Return a different resolution 9 cell for each index."""
    return h3.latlng_to_cell(36.0579 + index * 0.01, -112.1430, 9)


class FakeStore:
    """In-memory store with DynamoDB's promise: a refused commit changes nothing."""

    def __init__(self) -> None:
        self.reports: dict[str, dict] = {}
        self.counters: dict[str, dict] = {}
        self.conflicts_to_raise = 0
        self.error: Exception | None = None
        self.ids = Ids()

    def read_cell(self, cell_key: str) -> CellState:
        item = self.counters.get(cell_key)
        if item is None:
            return CellState(hours=(), version=None)
        return CellState(hours=tuple(item["report_hours"]), version=item["version"])

    def commit(self, commit: Commit) -> None:
        if self.error is not None:
            raise self.error
        if self.conflicts_to_raise:
            self.conflicts_to_raise -= 1
            raise VersionConflict
        if self._count(commit.visitor_day_key) >= VISITOR_DAILY_LIMIT:
            raise LimitReached(Limit.VISITOR_DAY)
        if self._count(commit.system_day_key) >= SYSTEM_DAILY_LIMIT:
            raise LimitReached(Limit.SYSTEM_DAY)
        current = self.counters.get(commit.cell_key)
        if (current["version"] if current else None) != commit.cell_version:
            raise VersionConflict

        self.reports[commit.report_item["report_id"]] = dict(commit.report_item)
        for key in (commit.visitor_day_key, commit.system_day_key):
            self.counters[key] = {
                "counter_key": key,
                "count": self._count(key) + 1,
                "expires_at_epoch": commit.counter_expires_at_epoch,
            }
        self.counters[commit.cell_key] = {
            "counter_key": commit.cell_key,
            "report_hours": list(commit.cell_hours),
            "version": (commit.cell_version or 0) + 1,
            "expires_at_epoch": commit.cell_expires_at_epoch,
        }

    def _count(self, key: str) -> int:
        return self.counters.get(key, {}).get("count", 0)


def _body(**overrides) -> dict:
    body = {
        "cell": CELL,
        "carrier": "T-Mobile",
        "had_signal": True,
        "report_hour_utc": THIS_HOUR.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    body.update(overrides)
    return body


def _event(body, visitor_id: str | None = VISITOR, encode: bool = False) -> dict:
    raw = body if isinstance(body, str) else json.dumps(body)
    headers = {"content-type": "application/json"}
    if visitor_id is not None:
        headers["x-visitor-id"] = visitor_id
    return {
        "version": "2.0",
        "routeKey": "POST /reports",
        "rawPath": "/reports",
        "headers": headers,
        "body": base64.b64encode(raw.encode()).decode() if encode else raw,
        "isBase64Encoded": encode,
        "requestContext": {"http": {"method": "POST", "path": "/reports"}},
    }


class Ids:
    def __init__(self) -> None:
        self.next = 0

    def __call__(self) -> str:
        self.next += 1
        return f"report-{self.next:04d}"


def _send(store, body=None, visitor_id=VISITOR, now=NOW, encode=False) -> dict:
    return reports.handle(
        _event(_body() if body is None else body, visitor_id, encode),
        store=store,
        load_secret=lambda: SECRET,
        now=now,
        new_report_id=store.ids,
    )


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _hour(hours_before_this_hour: int) -> str:
    return (THIS_HOUR - timedelta(hours=hours_before_this_hour)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_code(response: dict) -> str:
    return json.loads(response["body"])["error"]["code"]


# --- Accepting a report ------------------------------------------------------------------


def test_a_valid_report_is_accepted_and_stored_without_any_visitor_identity(store):
    response = _send(store)

    assert response["statusCode"] == 202
    assert json.loads(response["body"]) == {"status": "accepted"}
    assert list(store.reports.values()) == [
        {
            "report_id": "report-0001",
            "h3_cell_res9": CELL,
            "carrier": "T-Mobile",
            "had_signal": True,
            "report_hour_utc": "2026-11-09T18:00:00Z",
        }
    ]


def test_a_base64_encoded_body_is_read_like_a_plain_one(store):
    assert _send(store, encode=True)["statusCode"] == 202


def test_the_raw_visitor_id_is_never_stored(store):
    _send(store)

    stored = json.dumps([store.reports, store.counters])
    assert VISITOR not in stored


def test_the_cell_is_not_stored_in_the_counters(store):
    _send(store)

    assert CELL not in json.dumps(store.counters)


def test_the_visitor_hash_is_keyed_by_the_secret():
    first = reports.visitor_hash(SECRET, VISITOR)

    assert first == reports.visitor_hash(SECRET, VISITOR)
    assert first != reports.visitor_hash(b"another-fake-key", VISITOR)
    assert first != reports.visitor_hash(SECRET, OTHER_VISITOR)
    assert VISITOR not in first


# --- Limit: 10 a day per visitor, by the report's own UTC day ------------------------------


def test_the_eleventh_report_in_a_utc_day_from_one_visitor_is_refused(store):
    for index in range(VISITOR_DAILY_LIMIT):
        assert _send(store, _body(cell=_cell_near(index)))["statusCode"] == 202

    refused = _send(store, _body(cell=_cell_near(99)))

    assert refused["statusCode"] == 429
    assert _error_code(refused) == "report_limit_exceeded"
    assert "10 reports" in json.loads(refused["body"])["error"]["message"]
    assert len(store.reports) == VISITOR_DAILY_LIMIT


def test_another_visitor_is_not_held_back_by_the_first_visitors_limit(store):
    for index in range(VISITOR_DAILY_LIMIT):
        _send(store, _body(cell=_cell_near(index)))

    assert _send(store, _body(cell=_cell_near(99)), visitor_id=OTHER_VISITOR)["statusCode"] == 202


def test_a_batch_sent_after_being_offline_is_judged_by_its_report_hours(store):
    """Ten reports from yesterday and one from today all arrive now: none is refused."""
    yesterday = THIS_HOUR - timedelta(days=1)
    for index in range(VISITOR_DAILY_LIMIT):
        hour = (yesterday - timedelta(minutes=index * 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = _body(cell=_cell_near(index), report_hour_utc=hour)
        assert _send(store, body)["statusCode"] == 202

    assert _send(store, _body(cell=_cell_near(50)))["statusCode"] == 202


# --- Limit: one report per cell per visitor every 24 hours ---------------------------------


def test_a_second_report_for_the_same_cell_within_24_hours_is_refused(store):
    assert _send(store, _body(report_hour_utc=_hour(23)))["statusCode"] == 202

    refused = _send(store)

    assert refused["statusCode"] == 429
    assert "same place" in json.loads(refused["body"])["error"]["message"]


def test_a_report_for_the_same_cell_24_hours_later_is_accepted(store):
    assert _send(store, _body(report_hour_utc=_hour(24)))["statusCode"] == 202

    assert _send(store)["statusCode"] == 202


def test_an_earlier_report_that_arrives_later_is_still_checked_against_the_24_hours(store):
    assert _send(store)["statusCode"] == 202

    assert _send(store, _body(report_hour_utc=_hour(5)))["statusCode"] == 429


def test_the_cell_rule_remembers_every_recent_hour_not_only_the_last(store):
    """Reports at -40 h and -10 h are accepted; -16 h is 6 hours from -10 h."""
    assert _send(store, _body(report_hour_utc=_hour(10)))["statusCode"] == 202
    assert _send(store, _body(report_hour_utc=_hour(40)))["statusCode"] == 202

    assert _send(store, _body(report_hour_utc=_hour(16)))["statusCode"] == 429


def test_another_visitor_may_report_the_same_cell(store):
    _send(store)

    assert _send(store, visitor_id=OTHER_VISITOR)["statusCode"] == 202


def test_a_cell_conflict_from_a_parallel_request_is_retried(store):
    store.conflicts_to_raise = 1

    assert _send(store)["statusCode"] == 202


def test_endless_cell_conflicts_answer_dependency_unavailable(store):
    store.conflicts_to_raise = 100

    response = _send(store)

    assert response["statusCode"] == 503
    assert _error_code(response) == "dependency_unavailable"


# --- Limit: 50 a day for the whole system --------------------------------------------------


def test_the_fifty_first_report_in_a_utc_day_is_refused_for_everyone(store):
    for index in range(SYSTEM_DAILY_LIMIT):
        visitor = f"{index:032x}"
        assert _send(store, visitor_id=visitor)["statusCode"] == 202

    refused = _send(store, visitor_id=OTHER_VISITOR)

    assert refused["statusCode"] == 429
    assert "for today" in json.loads(refused["body"])["error"]["message"]


def test_the_system_counter_holds_no_visitor_hash(store):
    _send(store)

    system_items = [item for key, item in store.counters.items() if key.startswith("system#")]
    assert system_items
    assert reports.visitor_hash(SECRET, VISITOR) not in json.dumps(system_items)


# --- Report hour window (ADR 0026) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("report_hour", "arrival", "status"),
    [
        ("2026-11-07T19:00:00Z", datetime(2026, 11, 9, 19, 0, tzinfo=UTC), 202),
        ("2026-11-07T19:00:00Z", datetime(2026, 11, 9, 19, 1, tzinfo=UTC), 400),
        ("2026-11-09T19:00:00Z", datetime(2026, 11, 9, 18, 0, tzinfo=UTC), 202),
        ("2026-11-09T19:00:00Z", datetime(2026, 11, 9, 17, 59, tzinfo=UTC), 400),
    ],
    ids=["48h-old", "over-48h-old", "1h-ahead", "over-1h-ahead"],
)
def test_a_report_hour_must_be_within_48_hours_before_and_1_hour_after_arrival(
    store, report_hour, arrival, status
):
    response = _send(store, _body(report_hour_utc=report_hour), now=arrival)

    assert response["statusCode"] == status


def test_counters_expire_72_hours_after_the_end_of_their_utc_day():
    day_start = int(datetime(2026, 11, 9, tzinfo=UTC).timestamp())

    expiry = reports.counter_expiry_epoch(day_start)

    assert expiry == int(datetime(2026, 11, 13, tzinfo=UTC).timestamp())


def test_stored_counters_carry_that_expiry(store):
    _send(store)

    expected = int(datetime(2026, 11, 13, tzinfo=UTC).timestamp())
    assert {item["expires_at_epoch"] for item in store.counters.values()} == {expected}


# --- Invalid requests ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        json.dumps(_body(extra="field")),
        json.dumps({k: v for k, v in _body().items() if k != "carrier"}),
        json.dumps(_body(had_signal="yes")),
        json.dumps(_body(had_signal=1)),
        json.dumps(_body(carrier="Acme Mobile")),
        json.dumps(_body(cell="not-a-cell")),
        json.dumps(_body(cell=h3.latlng_to_cell(36.0579, -112.1430, 8))),
        json.dumps(_body(report_hour_utc="2026-11-09T18:30:00Z")),
        json.dumps(_body(report_hour_utc="2026-11-09T18:00:00")),
        json.dumps(_body(report_hour_utc="2026-11-09T11:00:00-07:00")),
        json.dumps(_body(cell=CELL + " " * 2000)),
    ],
    ids=[
        "not-json",
        "not-an-object",
        "extra-field",
        "missing-field",
        "signal-as-text",
        "signal-as-number",
        "unknown-carrier",
        "not-a-cell",
        "resolution-8-cell",
        "not-on-the-hour",
        "no-time-zone",
        "not-utc",
        "too-long",
    ],
)
def test_an_invalid_body_is_refused_and_nothing_is_stored(store, body):
    response = _send(store, body)

    assert response["statusCode"] == 400
    assert _error_code(response) == "invalid_request"
    assert store.reports == {}
    assert store.counters == {}


@pytest.mark.parametrize(
    "visitor_id",
    [None, "", "0123", "0123456789ABCDEF0123456789ABCDEF", "g" * 32, VISITOR + "0"],
)
def test_a_missing_or_malformed_visitor_id_is_refused(store, visitor_id):
    response = _send(store, visitor_id=visitor_id)

    assert response["statusCode"] == 400
    assert _error_code(response) == "invalid_request"
    assert store.reports == {}


def test_error_messages_never_echo_the_visitor_id_or_the_body(store):
    response = _send(store, json.dumps(_body(carrier=VISITOR)))

    assert VISITOR not in response["body"]


# --- Store and secret failures -------------------------------------------------------------


def test_a_store_failure_answers_dependency_unavailable(store):
    store.error = StoreUnavailable("throttled")

    response = _send(store)

    assert response["statusCode"] == 503
    assert _error_code(response) == "dependency_unavailable"


def test_a_missing_secret_answers_dependency_unavailable(store):
    def no_secret() -> bytes:
        raise StoreUnavailable("parameter missing")

    response = reports.handle(
        _event(_body()), store=store, load_secret=no_secret, now=NOW, new_report_id=Ids()
    )

    assert response["statusCode"] == 503
    assert store.reports == {}


# --- DynamoDB store ------------------------------------------------------------------------


class RecordingClient:
    """Stands in for the boto3 DynamoDB client: records calls, returns or raises as set."""

    def __init__(self, item: dict | None = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.item = item
        self.error = error

    def get_item(self, **kwargs) -> dict:
        self.calls.append(("get_item", kwargs))
        return {} if self.item is None else {"Item": self.item}

    def transact_write_items(self, **kwargs) -> dict:
        self.calls.append(("transact_write_items", kwargs))
        if self.error is not None:
            raise self.error
        return {}


def _commit(cell_version: int | None = None) -> Commit:
    return Commit(
        report_item={
            "report_id": "report-0001",
            "h3_cell_res9": CELL,
            "carrier": "T-Mobile",
            "had_signal": False,
            "report_hour_utc": "2026-11-09T18:00:00Z",
        },
        visitor_day_key="visitor#abc#2026-11-09",
        system_day_key="system#2026-11-09",
        cell_key="cell#def",
        cell_hours=(1_762_711_200,),
        cell_version=cell_version,
        counter_expires_at_epoch=1_763_000_000,
        cell_expires_at_epoch=1_763_000_000,
    )


def _cancelled(*codes: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
            "CancellationReasons": [{"Code": code} for code in codes],
        },
        "TransactWriteItems",
    )


def test_the_dynamodb_store_writes_report_and_all_counters_in_one_transaction():
    client = RecordingClient()

    DynamoReportStore(client, "reports-table", "counters-table").commit(_commit())

    [(name, request)] = client.calls
    assert name == "transact_write_items"
    items = request["TransactItems"]
    assert [next(iter(item)) for item in items] == ["Put", "Update", "Update", "Put"]
    report, visitor, system, cell = (next(iter(item.values())) for item in items)
    assert report["TableName"] == "reports-table"
    assert report["Item"]["had_signal"] == {"BOOL": False}
    assert set(report["Item"]) == {
        "report_id",
        "h3_cell_res9",
        "carrier",
        "had_signal",
        "report_hour_utc",
    }
    assert "attribute_not_exists" in report["ConditionExpression"]
    assert {visitor["TableName"], system["TableName"], cell["TableName"]} == {"counters-table"}
    assert visitor["Key"] == {"counter_key": {"S": "visitor#abc#2026-11-09"}}
    assert {"N": str(VISITOR_DAILY_LIMIT)} in visitor["ExpressionAttributeValues"].values()
    assert system["Key"] == {"counter_key": {"S": "system#2026-11-09"}}
    assert {"N": str(SYSTEM_DAILY_LIMIT)} in system["ExpressionAttributeValues"].values()
    assert cell["Item"]["report_hours"] == {"L": [{"N": "1762711200"}]}
    assert cell["Item"]["version"] == {"N": "1"}
    assert "attribute_not_exists" in cell["ConditionExpression"]


def test_the_dynamodb_store_checks_the_cell_version_it_read():
    client = RecordingClient()

    DynamoReportStore(client, "reports-table", "counters-table").commit(_commit(cell_version=3))

    cell = client.calls[0][1]["TransactItems"][3]["Put"]
    assert cell["Item"]["version"] == {"N": "4"}
    assert {"N": "3"} in cell["ExpressionAttributeValues"].values()


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        (("None", "ConditionalCheckFailed", "None", "None"), LimitReached(Limit.VISITOR_DAY)),
        (("None", "None", "ConditionalCheckFailed", "None"), LimitReached(Limit.SYSTEM_DAY)),
        (("None", "None", "None", "ConditionalCheckFailed"), VersionConflict()),
        (("None", "None", "None", "TransactionConflict"), VersionConflict()),
        (("None", "ThrottlingError", "None", "None"), StoreUnavailable()),
    ],
)
def test_the_dynamodb_store_names_why_a_transaction_was_cancelled(codes, expected):
    client = RecordingClient(error=_cancelled(*codes))
    store = DynamoReportStore(client, "reports-table", "counters-table")

    with pytest.raises(type(expected)) as raised:
        store.commit(_commit())

    if isinstance(expected, LimitReached):
        assert raised.value.limit is expected.limit


def test_any_other_dynamodb_error_is_store_unavailable():
    error = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow"}},
        "TransactWriteItems",
    )
    store = DynamoReportStore(RecordingClient(error=error), "reports-table", "counters-table")

    with pytest.raises(StoreUnavailable):
        store.commit(_commit())


def test_the_dynamodb_store_reads_a_cell_with_a_consistent_read():
    client = RecordingClient(
        item={
            "counter_key": {"S": "cell#def"},
            "report_hours": {"L": [{"N": "100"}, {"N": "200"}]},
            "version": {"N": "2"},
        }
    )

    state = DynamoReportStore(client, "reports-table", "counters-table").read_cell("cell#def")

    assert state == CellState(hours=(100, 200), version=2)
    [(name, request)] = client.calls
    assert name == "get_item"
    assert request["ConsistentRead"] is True
    assert request["Key"] == {"counter_key": {"S": "cell#def"}}


def test_the_dynamodb_store_reads_a_missing_cell_as_empty():
    store = DynamoReportStore(RecordingClient(), "reports-table", "counters-table")

    assert store.read_cell("cell#none") == CellState(hours=(), version=None)


# --- Contract ------------------------------------------------------------------------------


def test_the_report_fields_match_report_in_in_the_contract():
    from pathlib import Path

    import yaml

    contract = Path(__file__).resolve().parents[3] / "docs" / "trip-planner" / "openapi.yaml"
    spec = yaml.safe_load(contract.read_text(encoding="utf-8"))
    report_in = spec["components"]["schemas"]["ReportIn"]

    assert set(report_in["properties"]) == reports.REPORT_FIELDS
    assert set(report_in["required"]) == reports.REPORT_FIELDS
    assert report_in["additionalProperties"] is False
    assert set(spec["paths"]["/reports"]["post"]["responses"]) == {"202", "400", "429", "503"}
