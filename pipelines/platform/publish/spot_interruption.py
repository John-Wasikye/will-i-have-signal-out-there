"""Reads the two-minute spot interruption warning that AWS sends before it takes a box back.

The handler only records which box is affected and when it will stop. Every job is safe
to rerun, so no work needs saving first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from timeutil import require_utc

WARNING_SOURCE = "aws.ec2"
WARNING_DETAIL_TYPE = "EC2 Spot Instance Interruption Warning"
WARNING_WINDOW = timedelta(minutes=2)


@dataclass(frozen=True)
class SpotWarning:
    """The box that AWS is about to take back, and when it stops."""

    instance_id: str
    action: str
    warned_at_utc: datetime
    stops_at_utc: datetime


def parse_interruption_warning(event: dict) -> SpotWarning:
    """Turn an EventBridge spot warning into a SpotWarning.

    Raises ValueError when the event is another kind of event or has no instance ID.
    """
    if event.get("source") != WARNING_SOURCE or event.get("detail-type") != WARNING_DETAIL_TYPE:
        raise ValueError("not a spot interruption warning")

    detail = event.get("detail", {})
    instance_id = detail.get("instance-id")
    if not instance_id:
        raise ValueError("the warning has no instance-id")

    warned_at = require_utc(
        datetime.fromisoformat(event["time"].replace("Z", "+00:00")),
        "time",
    )
    return SpotWarning(
        instance_id=instance_id,
        action=detail["instance-action"],
        warned_at_utc=warned_at,
        stops_at_utc=warned_at + WARNING_WINDOW,
    )
