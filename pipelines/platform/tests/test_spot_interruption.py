"""Tests for the handler of the two-minute spot interruption warning.

AWS sends an EventBridge event when it is about to take back a spot instance. The
handler reads that event and says which box is affected and when it will stop. Every
job is safe to rerun, so the handler only has to record the warning, not save work.
"""

from datetime import UTC, timedelta

import pytest
from spot_interruption import parse_interruption_warning

EVENT = {
    "version": "0",
    "source": "aws.ec2",
    "detail-type": "EC2 Spot Instance Interruption Warning",
    "time": "2026-10-10T11:30:00Z",
    "region": "us-east-1",
    "detail": {"instance-id": "i-0123456789abcdef0", "instance-action": "stop"},
}


def test_the_warning_names_the_box_and_its_action():
    warning = parse_interruption_warning(EVENT)
    assert warning.instance_id == "i-0123456789abcdef0"
    assert warning.action == "stop"


def test_the_deadline_is_two_minutes_after_the_warning():
    warning = parse_interruption_warning(EVENT)
    assert warning.warned_at_utc.tzinfo == UTC
    assert warning.stops_at_utc - warning.warned_at_utc == timedelta(minutes=2)


def test_an_event_of_another_type_is_refused():
    other = {**EVENT, "detail-type": "EC2 Instance State-change Notification"}
    with pytest.raises(ValueError, match="not a spot interruption warning"):
        parse_interruption_warning(other)


def test_an_event_from_another_source_is_refused():
    other = {**EVENT, "source": "aws.s3"}
    with pytest.raises(ValueError, match="not a spot interruption warning"):
        parse_interruption_warning(other)


def test_a_warning_without_an_instance_id_is_refused():
    broken = {**EVENT, "detail": {"instance-action": "stop"}}
    with pytest.raises(ValueError, match="instance-id"):
        parse_interruption_warning(broken)
