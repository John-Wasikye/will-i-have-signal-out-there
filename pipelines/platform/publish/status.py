"""Status document for the status page (docs/platform/contracts/status_json.yaml).

The state of each pipeline is decided here, in one place:
- failed: the latest run failed
- late: there is no good run yet, or the last good run is older than its target
- ok: the last good run is within its target
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from timeutil import format_utc, require_utc


@dataclass(frozen=True)
class PipelineStatus:
    """What the status page shows for one pipeline."""

    name: str
    freshness_target_hours: float
    last_good_run_utc: datetime | None = None
    last_row_count: int | None = None
    last_run_failed: bool = False
    incident_url: str | None = None


def pipeline_state(pipeline: PipelineStatus, now_utc: datetime) -> str:
    """Return ok, late or failed for one pipeline."""
    require_utc(now_utc, "now_utc")
    if pipeline.last_run_failed:
        return "failed"
    if pipeline.last_good_run_utc is None:
        return "late"
    age = now_utc - require_utc(pipeline.last_good_run_utc, "last_good_run_utc")
    if age > timedelta(hours=pipeline.freshness_target_hours):
        return "late"
    return "ok"


def build_status_document(pipelines: Sequence[PipelineStatus], now_utc: datetime) -> dict:
    """Build the status.json document. Keys match the contract exactly."""
    entries = []
    for pipeline in pipelines:
        entry: dict[str, object] = {
            "name": pipeline.name,
            "state": pipeline_state(pipeline, now_utc),
            "freshness_target_hours": pipeline.freshness_target_hours,
        }
        if pipeline.last_good_run_utc is not None:
            entry["last_good_run_utc"] = format_utc(pipeline.last_good_run_utc)
        if pipeline.last_row_count is not None:
            entry["last_row_count"] = pipeline.last_row_count
        if pipeline.incident_url is not None:
            entry["incident_url"] = pipeline.incident_url
        entries.append(entry)
    return {"generated_at_utc": format_utc(now_utc), "pipelines": entries}


def write_status(pipelines: Sequence[PipelineStatus], now_utc: datetime, path: Path) -> dict:
    """Write status.json atomically and return the document that was written."""
    document = build_status_document(pipelines, now_utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return document
