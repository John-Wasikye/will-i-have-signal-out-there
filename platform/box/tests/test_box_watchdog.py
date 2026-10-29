"""Tests for the box watchdog: when to stop the session box, and how it finds out.

The box runs the nightly pipelines and then switches itself off, so it only bills while it
works. The watchdog watches for three reasons to stop, in this order of priority:
1. AWS is about to take the spot instance back (a two-minute warning)
2. the nightly run has finished
3. the box has been up for the 2-hour nightly maximum
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from box_watchdog import (
    Action,
    Decision,
    RunProgress,
    box_boot_time,
    carry_out_stop,
    combined_progress,
    decide,
    fetch_spot_stop_time,
    fetch_work_session_end,
    file_stop_incident,
    http_request,
    is_nightly_boot,
    list_runs_command,
    parse_args,
    parse_session_end,
    parse_spot_notice,
    run_progress,
    stop_incident,
    watch,
)

STARTED = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)


def _run(state: str, run_after: str, **extra) -> dict:
    """One entry of `airflow dags list-runs --output json`."""
    return {
        "dag_id": "platform_skeleton_nightly",
        "run_id": f"scheduled__{run_after}",
        "state": state,
        "run_after": run_after,
        "logical_date": run_after,
        "start_date": run_after,
        "end_date": "",
        **extra,
    }


def test_with_no_runs_yet_the_watchdog_is_waiting_for_one():
    assert run_progress("[]", STARTED) is RunProgress.WAITING


def test_a_run_from_before_the_box_started_is_ignored():
    runs = json.dumps([_run("success", "2026-10-09T10:00:00+00:00")])

    assert run_progress(runs, STARTED) is RunProgress.WAITING


def test_tonights_run_counts_when_the_box_boots_after_its_scheduled_time():
    # On 2026-10-28 the box booted at 10:02:59 after spot capacity retries, and the 10:00 run
    # was ignored for 90 minutes.
    late_boot = datetime(2026, 10, 10, 10, 2, 59, tzinfo=UTC)
    runs = json.dumps([_run("failed", "2026-10-10T10:00:00+00:00")])

    assert run_progress(runs, late_boot) is RunProgress.FAILED


def test_a_queued_or_running_run_means_the_pipelines_are_still_working():
    for state in ("queued", "running"):
        runs = json.dumps([_run(state, "2026-10-10T10:00:00+00:00")])

        assert run_progress(runs, STARTED) is RunProgress.RUNNING


def test_a_successful_run_is_reported_as_succeeded():
    runs = json.dumps([_run("success", "2026-10-10T10:00:05+00:00")])

    assert run_progress(runs, STARTED) is RunProgress.SUCCEEDED


def test_a_failed_run_is_reported_as_failed():
    runs = json.dumps([_run("failed", "2026-10-10T10:00:05+00:00")])

    assert run_progress(runs, STARTED) is RunProgress.FAILED


def test_the_newest_run_after_the_box_started_decides():
    runs = json.dumps(
        [
            _run("success", "2026-10-09T10:00:00+00:00"),
            _run("running", "2026-10-10T10:00:05+00:00"),
        ]
    )

    assert run_progress(runs, STARTED) is RunProgress.RUNNING


def test_an_unknown_run_state_is_an_error_not_a_guess():
    runs = json.dumps([_run("mystery", "2026-10-10T10:00:05+00:00")])

    with pytest.raises(ValueError, match="unknown run state"):
        run_progress(runs, STARTED)


@pytest.mark.parametrize(
    ("progresses", "expected"),
    [
        ([RunProgress.SUCCEEDED, RunProgress.SUCCEEDED], RunProgress.SUCCEEDED),
        ([RunProgress.SUCCEEDED, RunProgress.FAILED], RunProgress.FAILED),
        ([RunProgress.FAILED, RunProgress.RUNNING], RunProgress.RUNNING),
        ([RunProgress.SUCCEEDED, RunProgress.WAITING], RunProgress.WAITING),
        ([RunProgress.WAITING, RunProgress.RUNNING], RunProgress.RUNNING),
        ([RunProgress.SUCCEEDED], RunProgress.SUCCEEDED),
    ],
)
def test_the_night_is_finished_only_when_every_nightly_dag_has_finished(progresses, expected):
    # A DAG that failed early must not power the box off while another is still working.
    assert combined_progress(progresses) is expected


def test_combined_progress_needs_at_least_one_dag():
    with pytest.raises(ValueError, match="at least one"):
        combined_progress([])


def test_run_progress_refuses_a_naive_box_start_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        run_progress("[]", datetime(2026, 10, 10, 10, 0))


def _decide(minutes: float, progress: RunProgress, spot_stop=None):
    return decide(
        now_utc=STARTED + timedelta(minutes=minutes),
        box_started_utc=STARTED,
        progress=progress,
        spot_stop_utc=spot_stop,
    )


def test_it_keeps_waiting_while_the_run_works_inside_the_limit():
    assert _decide(45, RunProgress.RUNNING).action is Action.KEEP_WAITING


def test_it_keeps_waiting_for_a_run_that_has_not_started_yet():
    assert _decide(3, RunProgress.WAITING).action is Action.KEEP_WAITING


def test_it_stops_when_the_run_succeeded():
    assert _decide(40, RunProgress.SUCCEEDED).action is Action.STOP_FINISHED


def test_it_stops_when_the_run_failed_because_the_failure_is_already_recorded():
    assert _decide(40, RunProgress.FAILED).action is Action.STOP_FINISHED


def test_it_stops_at_the_two_hour_maximum_even_while_the_run_is_still_working():
    decision = _decide(120, RunProgress.RUNNING)

    assert decision.action is Action.STOP_MAXIMUM
    assert "2 hour" in decision.reason


def test_it_stops_at_the_maximum_when_no_run_ever_started():
    assert _decide(120, RunProgress.WAITING).action is Action.STOP_MAXIMUM


def test_a_run_that_finished_is_not_called_a_timeout_even_if_the_watchdog_noticed_late():
    assert _decide(125, RunProgress.SUCCEEDED).action is Action.STOP_FINISHED


def test_a_spot_warning_beats_everything_else():
    decision = _decide(
        30,
        RunProgress.SUCCEEDED,
        spot_stop=STARTED + timedelta(minutes=32),
    )

    assert decision.action is Action.STOP_SPOT_WARNING
    assert "2026-10-10T10:32:00Z" in decision.reason


def test_decide_refuses_naive_times():
    with pytest.raises(ValueError, match="timezone-aware"):
        decide(datetime(2026, 10, 10, 10, 5), STARTED, RunProgress.RUNNING, None)


def test_a_spot_notice_gives_the_time_the_box_will_stop():
    body = json.dumps({"action": "stop", "time": "2026-10-10T11:32:00Z"})

    assert parse_spot_notice(body) == datetime(2026, 10, 10, 11, 32, tzinfo=UTC)


def test_a_notice_that_is_not_json_is_refused():
    with pytest.raises(ValueError, match="spot notice"):
        parse_spot_notice("<html>not json</html>")


def test_a_notice_without_a_time_is_refused():
    with pytest.raises(ValueError, match="time"):
        parse_spot_notice(json.dumps({"action": "stop"}))


class FakeMetadata:
    """Answers the two instance metadata calls, and records them."""

    def __init__(self, notice_status=404, notice_body=""):
        self.notice_status = notice_status
        self.notice_body = notice_body
        self.calls = []

    def __call__(self, method, url, headers):
        self.calls.append((method, url, dict(headers)))
        if method == "PUT":
            return 200, "the-token"
        return self.notice_status, self.notice_body


def test_the_metadata_service_is_asked_with_a_token():
    metadata = FakeMetadata()

    fetch_spot_stop_time(metadata)

    put, get = metadata.calls
    assert put[0] == "PUT" and put[1].endswith("/latest/api/token")
    assert "X-aws-ec2-metadata-token-ttl-seconds" in put[2]
    assert get[0] == "GET" and get[1].endswith("/latest/meta-data/spot/instance-action")
    assert get[2]["X-aws-ec2-metadata-token"] == "the-token"


def test_no_notice_means_no_stop_time():
    assert fetch_spot_stop_time(FakeMetadata(notice_status=404)) is None


def test_a_notice_gives_the_stop_time():
    body = json.dumps({"action": "stop", "time": "2026-10-10T11:32:00Z"})

    stop = fetch_spot_stop_time(FakeMetadata(notice_status=200, notice_body=body))

    assert stop == datetime(2026, 10, 10, 11, 32, tzinfo=UTC)


def test_an_unexpected_answer_from_the_metadata_service_is_an_error():
    with pytest.raises(OSError, match="500"):
        fetch_spot_stop_time(FakeMetadata(notice_status=500))


class Steps:
    """Records the order in which the stop steps run, and can make one of them fail."""

    def __init__(self, fail=()):
        self.order = []
        self.fail = set(fail)

    def _step(self, name):
        self.order.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} broke")

    def save_database(self):
        self._step("save_database")

    def record_incident(self, decision):
        self._step("record_incident")

    def send_alert(self, decision):
        self._step("send_alert")

    def power_off(self):
        self._step("power_off")


def _stop(steps, action):
    return carry_out_stop(
        Decision(action, "reason"),
        save_database=steps.save_database,
        record_incident=steps.record_incident,
        send_alert=steps.send_alert,
        power_off=steps.power_off,
    )


def test_a_finished_run_saves_the_database_then_powers_off_with_no_incident():
    steps = Steps()

    errors = _stop(steps, Action.STOP_FINISHED)

    assert steps.order == ["save_database", "power_off"]
    assert errors == []


def test_the_maximum_also_records_an_incident_and_emails_me():
    steps = Steps()

    _stop(steps, Action.STOP_MAXIMUM)

    assert steps.order == ["save_database", "record_incident", "send_alert", "power_off"]


def test_a_spot_warning_emails_me_but_records_no_incident():
    """Runbook PRB-3: AWS taking the box back is a note, not an incident; nothing broke."""
    steps = Steps()

    _stop(steps, Action.STOP_SPOT_WARNING)

    assert steps.order == ["save_database", "send_alert", "power_off"]


def test_powering_off_is_last_even_when_saving_the_database_fails():
    steps = Steps(fail={"save_database"})

    errors = _stop(steps, Action.STOP_MAXIMUM)

    assert steps.order == ["save_database", "record_incident", "send_alert", "power_off"]
    assert errors == ["save_database failed: save_database broke"]


def test_powering_off_still_happens_when_the_incident_cannot_be_recorded():
    steps = Steps(fail={"record_incident"})

    errors = _stop(steps, Action.STOP_MAXIMUM)

    assert steps.order[-1] == "power_off"
    assert errors == ["record_incident failed: record_incident broke"]


def test_the_email_is_still_sent_when_the_incident_cannot_be_recorded():
    steps = Steps(fail={"record_incident"})

    _stop(steps, Action.STOP_MAXIMUM)

    assert "send_alert" in steps.order


def test_powering_off_still_happens_when_the_email_cannot_be_sent():
    steps = Steps(fail={"send_alert"})

    errors = _stop(steps, Action.STOP_SPOT_WARNING)

    assert steps.order[-1] == "power_off"
    assert errors == ["send_alert failed: send_alert broke"]


def test_if_powering_off_fails_the_error_is_not_hidden():
    steps = Steps(fail={"power_off"})

    with pytest.raises(RuntimeError, match="power_off broke"):
        _stop(steps, Action.STOP_FINISHED)


class FakeClock:
    """A clock that moves only when the watchdog sleeps."""

    def __init__(self, start):
        self.current = start

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.current += timedelta(seconds=seconds)


def _watch(clock, progress, spot=lambda: None, stops=None):
    stops = [] if stops is None else stops
    decision = watch(
        now=clock.now,
        sleep=clock.sleep,
        box_started_utc=STARTED,
        get_progress=progress,
        get_spot_stop=spot,
        on_stop=stops.append,
        poll_seconds=30,
    )
    return decision, stops


def test_the_watchdog_waits_until_the_run_finishes_and_then_stops_once():
    clock = FakeClock(STARTED)
    answers = iter([RunProgress.WAITING, RunProgress.RUNNING, RunProgress.RUNNING])

    def progress():
        return next(answers, RunProgress.SUCCEEDED)

    decision, stops = _watch(clock, progress)

    assert decision.action is Action.STOP_FINISHED
    assert [d.action for d in stops] == [Action.STOP_FINISHED]
    assert clock.now() == STARTED + timedelta(seconds=30 * 3)


def test_the_watchdog_stops_at_the_maximum_if_the_run_never_finishes():
    clock = FakeClock(STARTED)

    decision, _ = _watch(clock, lambda: RunProgress.RUNNING)

    assert decision.action is Action.STOP_MAXIMUM
    assert clock.now() == STARTED + timedelta(hours=2)


def test_the_watchdog_acts_on_a_spot_warning_at_once():
    clock = FakeClock(STARTED)

    decision, _ = _watch(
        clock,
        lambda: RunProgress.RUNNING,
        spot=lambda: STARTED + timedelta(minutes=2),
    )

    assert decision.action is Action.STOP_SPOT_WARNING
    assert clock.now() == STARTED


def test_if_airflow_cannot_be_reached_the_watchdog_still_stops_at_the_maximum():
    clock = FakeClock(STARTED)

    def broken_progress():
        raise OSError("kubectl cannot reach the cluster")

    decision, _ = _watch(clock, broken_progress)

    assert decision.action is Action.STOP_MAXIMUM


def test_if_the_metadata_service_fails_the_watchdog_keeps_going():
    clock = FakeClock(STARTED)

    def broken_spot():
        raise OSError("metadata service unreachable")

    decision, _ = _watch(clock, lambda: RunProgress.SUCCEEDED, spot=broken_spot)

    assert decision.action is Action.STOP_FINISHED


def test_the_boot_time_is_the_current_time_minus_the_uptime():
    now = datetime(2026, 10, 10, 10, 20, 0, tzinfo=UTC)

    assert box_boot_time(now, uptime_seconds=1200.5) == now - timedelta(seconds=1200.5)


def test_the_two_hour_clock_starts_at_boot_not_when_the_watchdog_starts():
    now = datetime(2026, 10, 10, 10, 20, tzinfo=UTC)

    boot = box_boot_time(now, uptime_seconds=20 * 60)

    assert boot == STARTED


def test_the_boot_time_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        box_boot_time(datetime(2026, 10, 10, 10, 20), uptime_seconds=60)


def test_the_run_list_is_read_from_the_scheduler_pod():
    command = list_runs_command("airflow", "platform_skeleton_nightly")

    assert command == [
        "kubectl",
        "exec",
        "--namespace",
        "airflow",
        "airflow-scheduler-0",
        "--container",
        "scheduler",
        "--",
        "airflow",
        "dags",
        "list-runs",
        "platform_skeleton_nightly",
        "--output",
        "json",
    ]


def test_a_maximum_incident_says_the_run_reached_its_limit():
    decision = Decision(Action.STOP_MAXIMUM, "The nightly run reached its 2 hour maximum.")

    incident = stop_incident(decision, number=1, opened_utc=STARTED, pipeline="p")

    assert incident["reached_maximum_runtime"] is True
    assert incident["what_broke"] == "The nightly run reached its 2 hour maximum."
    assert incident["incident_id"] == "INC-2026-10-10-01"


@pytest.mark.parametrize("action", [Action.STOP_FINISHED, Action.STOP_SPOT_WARNING])
def test_only_the_maximum_makes_an_incident(action):
    with pytest.raises(ValueError, match="no incident"):
        stop_incident(Decision(action, "a reason"), 1, STARTED, "p")


class FakeLake:
    """An S3 bucket in memory: listing by prefix, and put_object with If-None-Match."""

    def __init__(self, keys):
        self.objects = {key: b"" for key in keys}

    def get_paginator(self, name):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803, boto3 parameter names
        found = [k for k in sorted(self.objects) if k.startswith(Prefix)]
        yield {"Contents": [{"Key": k} for k in found]} if found else {}

    def put_object(self, Bucket, Key, Body, IfNoneMatch=None, ContentType=None):  # noqa: N803
        assert IfNoneMatch == "*", "an incident must never replace an existing record"
        assert Key not in self.objects
        self.objects[Key] = Body


def test_a_stop_incident_is_filed_in_s3_after_the_ones_already_there(tmp_path):
    lake = FakeLake(
        [
            "platform/incidents/INC-2026-10-10-01.parquet",
            "platform/incidents/INC-2026-10-10-02.parquet",
            "platform/incidents/INC-2026-10-09-01.parquet",
        ]
    )
    decision = Decision(Action.STOP_MAXIMUM, "The nightly run reached its 2 hour maximum.")

    key = file_stop_incident(lake, "bucket", decision, STARTED, "p", tmp_path)

    assert key == "platform/incidents/INC-2026-10-10-03.parquet"
    assert key in lake.objects


class _Server:
    """A tiny local web server that stands in for the instance metadata service."""

    def __init__(self, routes):
        import http.server
        import threading

        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def _answer(self):
                seen.append((self.command, self.path, dict(self.headers)))
                status, body = routes.get((self.command, self.path), (404, ""))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body.encode())

            do_GET = do_PUT = _answer

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def test_the_web_request_returns_the_status_and_body():
    with _Server({("GET", "/hello"): (200, "hi")}) as server:
        assert http_request("GET", f"{server.url}/hello", {}) == (200, "hi")


def test_a_404_is_an_answer_not_an_error():
    with _Server({}) as server:
        assert http_request("GET", f"{server.url}/missing", {}) == (404, "")


def test_the_web_request_sends_its_headers_and_method():
    with _Server({("PUT", "/token"): (200, "t")}) as server:
        http_request("PUT", f"{server.url}/token", {"X-Test": "yes"})

    method, path, headers = server.seen[0]
    assert (method, path) == ("PUT", "/token")
    assert headers["X-Test"] == "yes"


def test_the_whole_spot_check_works_against_a_local_stand_in_for_the_metadata_service():
    notice = json.dumps({"action": "stop", "time": "2026-10-10T11:32:00Z"})
    routes = {
        ("PUT", "/latest/api/token"): (200, "tok"),
        ("GET", "/latest/meta-data/spot/instance-action"): (200, notice),
    }
    with _Server(routes) as server:
        stop = fetch_spot_stop_time(http_request, base_url=server.url)

    assert stop == datetime(2026, 10, 10, 11, 32, tzinfo=UTC)


TOPIC = "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"


def test_the_command_line_needs_a_bucket_and_has_sensible_defaults():
    args = parse_args(["--bucket", "lake", "--env", "dev", "--alert-topic-arn", TOPIC])

    assert args.bucket == "lake"
    assert args.env == "dev"
    assert args.alert_topic_arn == TOPIC
    assert args.namespace == "airflow"
    assert args.dag_ids == ["platform_skeleton_nightly"]
    assert args.poll_seconds == 30

    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["--bucket", "lake", "--env", "dev"])
    with pytest.raises(SystemExit):
        parse_args(["--bucket", "lake", "--env", "staging", "--alert-topic-arn", TOPIC])


def test_the_command_line_takes_every_nightly_dag_to_wait_for():
    args = parse_args(
        [
            "--bucket", "lake", "--env", "dev", "--alert-topic-arn", TOPIC,
            "--dag-id", "platform_skeleton_nightly", "--dag-id", "signal_phase_a_nightly",
        ]
    )  # fmt: skip

    assert args.dag_ids == ["platform_skeleton_nightly", "signal_phase_a_nightly"]


def test_a_boot_at_the_scheduled_time_is_the_nightly_run():
    assert is_nightly_boot(datetime(2026, 10, 10, 10, 2, tzinfo=UTC)) is True


def test_a_boot_from_a_retried_start_is_still_the_nightly_run():
    # With no spot capacity, the start schedule retries for up to 2 hours (until 12:00 UTC).
    assert is_nightly_boot(datetime(2026, 10, 10, 10, 40, tzinfo=UTC)) is True
    assert is_nightly_boot(datetime(2026, 10, 10, 12, 0, tzinfo=UTC)) is True


def test_a_boot_after_the_start_retries_end_is_not_the_nightly_run():
    assert is_nightly_boot(datetime(2026, 10, 10, 12, 1, tzinfo=UTC)) is False
    assert is_nightly_boot(datetime(2026, 10, 10, 15, 52, tzinfo=UTC)) is False


def test_a_boot_before_the_scheduled_time_is_a_work_session():
    assert is_nightly_boot(datetime(2026, 10, 10, 9, 55, tzinfo=UTC)) is False


def test_the_nightly_check_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        is_nightly_boot(datetime(2026, 10, 10, 10, 2))


WORK_SESSION_START = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)
WORK_SESSION_END = WORK_SESSION_START + timedelta(hours=4)


def test_a_work_session_is_never_stopped_for_finishing_or_for_the_nightly_maximum():
    for progress in RunProgress:
        decision = decide(
            now_utc=WORK_SESSION_START + timedelta(hours=3),
            box_started_utc=WORK_SESSION_START,
            progress=progress,
            spot_stop_utc=None,
            nightly=False,
            session_ends_utc=WORK_SESSION_END,
        )

        assert decision.action is Action.KEEP_WAITING


def test_a_work_session_stops_at_the_four_hour_session_limit():
    # The 14:00 UTC hard stop only bounds the nightly run. A session I start at another
    # time would otherwise run until the next 14:00 UTC (ADR-0013: 4 hours per session).
    decision = decide(
        now_utc=WORK_SESSION_START + timedelta(hours=4),
        box_started_utc=WORK_SESSION_START,
        progress=RunProgress.WAITING,
        spot_stop_utc=None,
        nightly=False,
        session_ends_utc=WORK_SESSION_END,
    )

    assert decision.action is Action.STOP_SESSION_LIMIT


def test_the_session_limit_saves_and_powers_off_without_an_incident_or_an_email():
    steps = Steps()

    errors = _stop(steps, Action.STOP_SESSION_LIMIT)

    assert steps.order == ["save_database", "power_off"]
    assert errors == []


def test_a_work_session_still_stops_for_a_spot_warning():
    decision = decide(
        now_utc=WORK_SESSION_START + timedelta(hours=1),
        box_started_utc=WORK_SESSION_START,
        progress=RunProgress.RUNNING,
        spot_stop_utc=WORK_SESSION_START + timedelta(hours=1, minutes=2),
        nightly=False,
        session_ends_utc=WORK_SESSION_END,
    )

    assert decision.action is Action.STOP_SPOT_WARNING


def test_the_watchdog_leaves_a_work_session_alone_until_a_spot_warning_comes():
    clock = FakeClock(WORK_SESSION_START)
    warnings = iter([None, None, None])

    def spot():
        return next(warnings, WORK_SESSION_START + timedelta(minutes=4))

    decision = watch(
        now=clock.now,
        sleep=clock.sleep,
        box_started_utc=WORK_SESSION_START,
        get_progress=lambda: RunProgress.SUCCEEDED,
        get_spot_stop=spot,
        on_stop=lambda d: None,
        poll_seconds=30,
        get_session_end=lambda: WORK_SESSION_END,
    )

    assert decision.action is Action.STOP_SPOT_WARNING
    assert clock.now() == WORK_SESSION_START + timedelta(seconds=90)


# --- A start nobody planned ------------------------------------------------------------------
#
# After AWS takes a spot box back, it starts the box again by itself once capacity returns,
# at any hour (on 2026-10-26 it did so at 15:52 UTC). A work session is one I plan: I tag the
# box with WorkSessionUntil before I start it. A boot outside the nightly window with no
# current tag is a start nobody planned, and the watchdog stops it at once.

UNPLANNED_BOOT = datetime(2026, 10, 26, 15, 52, tzinfo=UTC)


def _decide_outside_the_window(now, started, session_ends):
    return decide(
        now_utc=now,
        box_started_utc=started,
        progress=RunProgress.WAITING,
        spot_stop_utc=None,
        nightly=False,
        session_ends_utc=session_ends,
    )


def test_a_boot_outside_the_window_with_no_session_tag_is_stopped_at_once():
    decision = _decide_outside_the_window(
        UNPLANNED_BOOT + timedelta(minutes=1), UNPLANNED_BOOT, None
    )

    assert decision.action is Action.STOP_UNPLANNED


def test_a_session_tag_left_over_from_an_earlier_session_does_not_count():
    decision = _decide_outside_the_window(
        UNPLANNED_BOOT + timedelta(minutes=1), UNPLANNED_BOOT, UNPLANNED_BOOT - timedelta(hours=3)
    )

    assert decision.action is Action.STOP_UNPLANNED


def test_a_work_session_stops_at_the_end_time_i_tagged():
    ends = WORK_SESSION_START + timedelta(hours=2)

    before = _decide_outside_the_window(ends - timedelta(seconds=1), WORK_SESSION_START, ends)
    at = _decide_outside_the_window(ends, WORK_SESSION_START, ends)

    assert before.action is Action.KEEP_WAITING
    assert at.action is Action.STOP_SESSION_LIMIT


def test_a_tag_further_out_than_four_hours_still_stops_at_the_session_limit():
    decision = _decide_outside_the_window(
        WORK_SESSION_START + timedelta(hours=4),
        WORK_SESSION_START,
        WORK_SESSION_START + timedelta(hours=9),
    )

    assert decision.action is Action.STOP_SESSION_LIMIT


def test_the_nightly_run_ignores_the_session_tag():
    decision = decide(
        now_utc=STARTED + timedelta(minutes=5),
        box_started_utc=STARTED,
        progress=RunProgress.RUNNING,
        spot_stop_utc=None,
        nightly=True,
        session_ends_utc=None,
    )

    assert decision.action is Action.KEEP_WAITING


def test_an_unplanned_stop_saves_the_database_and_emails_me_without_an_incident():
    steps = Steps()

    errors = _stop(steps, Action.STOP_UNPLANNED)

    assert steps.order == ["save_database", "send_alert", "power_off"]
    assert errors == []


def _watch_outside_the_window(clock, started, get_session_end, poll_seconds=30):
    return watch(
        now=clock.now,
        sleep=clock.sleep,
        box_started_utc=started,
        get_progress=lambda: RunProgress.WAITING,
        get_spot_stop=lambda: None,
        on_stop=lambda d: None,
        poll_seconds=poll_seconds,
        get_session_end=get_session_end,
    )


def test_the_watchdog_stops_an_unplanned_boot_on_its_first_check():
    clock = FakeClock(UNPLANNED_BOOT)

    decision = _watch_outside_the_window(clock, UNPLANNED_BOOT, lambda: None)

    assert decision.action is Action.STOP_UNPLANNED
    assert clock.now() == UNPLANNED_BOOT


def test_if_the_session_tag_cannot_be_read_the_box_gets_the_four_hour_limit():
    # A failed read must not stop a session I planned, so it counts as a 4-hour session.
    clock = FakeClock(WORK_SESSION_START)

    def broken():
        raise OSError("the metadata service is not answering")

    decision = _watch_outside_the_window(clock, WORK_SESSION_START, broken, poll_seconds=60)

    assert decision.action is Action.STOP_SESSION_LIMIT
    assert clock.now() == WORK_SESSION_START + timedelta(hours=4)


def test_a_failed_read_keeps_the_last_session_end_it_read():
    clock = FakeClock(WORK_SESSION_START)
    ends = WORK_SESSION_START + timedelta(hours=1)
    answers = iter([ends])

    def flaky():
        try:
            return next(answers)
        except StopIteration:
            raise OSError("the metadata service is not answering") from None

    decision = _watch_outside_the_window(clock, WORK_SESSION_START, flaky, poll_seconds=60)

    assert decision.action is Action.STOP_SESSION_LIMIT
    assert clock.now() == ends


def test_the_session_end_is_read_from_the_instance_tag_with_a_token():
    metadata = FakeMetadata(notice_status=200, notice_body="2026-10-26T20:00:00Z")

    ends = fetch_work_session_end(metadata)

    put, get = metadata.calls
    assert put[0] == "PUT" and put[1].endswith("/latest/api/token")
    assert get[0] == "GET" and get[1].endswith("/latest/meta-data/tags/instance/WorkSessionUntil")
    assert get[2]["X-aws-ec2-metadata-token"] == "the-token"
    assert ends == datetime(2026, 10, 26, 20, 0, tzinfo=UTC)


def test_no_session_tag_means_no_session():
    assert fetch_work_session_end(FakeMetadata(notice_status=404)) is None


def test_an_unexpected_answer_for_the_session_tag_is_an_error():
    with pytest.raises(OSError, match="500"):
        fetch_work_session_end(FakeMetadata(notice_status=500))


def test_a_session_end_must_be_a_time_with_a_timezone():
    assert parse_session_end("2026-10-26T20:00:00+00:00") == datetime(
        2026, 10, 26, 20, 0, tzinfo=UTC
    )
    with pytest.raises(ValueError):
        parse_session_end("2026-10-26T20:00:00")
    with pytest.raises(ValueError):
        parse_session_end("tonight")
