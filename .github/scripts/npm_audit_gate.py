"""Fail the site's package audit on any advisory I have not accepted, with an expiry date.

Usage: python3 npm_audit_gate.py <npm audit --json report> <exception list>

`npm audit` has no way to skip one advisory, so CI saves its JSON report and this script decides.
It blocks every advisory of moderate severity or worse (the level the old step used) unless the
exception list names its GitHub advisory ID with an expiry date that has not passed. The list
works like `.trivyignore`: one `GHSA-... exp:YYYY-MM-DD` line per advisory, with a comment that
gives the reason, so the check fails again on the expiry date. Standard library only, because the
CI job installs no Python packages.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

BLOCKING = {"moderate", "high", "critical"}


def read_exceptions(text: str) -> dict[str, date]:
    """Return each accepted advisory ID with its expiry date; refuse a line without one."""
    exceptions = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("exp:"):
            raise ValueError(f"line {number}: expected 'GHSA-... exp:YYYY-MM-DD', got {line!r}")
        exceptions[parts[0]] = date.fromisoformat(parts[1].removeprefix("exp:"))
    return exceptions


def blocking_findings(report: dict, exceptions: dict[str, date], today: date) -> list[str]:
    """Return one line per advisory that should fail the check, or none."""
    if "error" in report:
        summary = report["error"].get("summary", report["error"])
        return [f"npm audit did not run: {summary}"]
    findings = {}
    for package in report.get("vulnerabilities", {}).values():
        # A string in `via` names a flagged dependency, listed under its own package.
        for advisory in (via for via in package.get("via", []) if isinstance(via, dict)):
            if advisory["severity"] not in BLOCKING:
                continue
            ghsa = advisory["url"].rsplit("/", 1)[-1]
            expiry = exceptions.get(ghsa)
            if expiry is not None and today <= expiry:
                continue
            note = f" (exception expired {expiry.isoformat()})" if expiry else ""
            findings[ghsa] = (
                f"{advisory['name']} {advisory['range']}: {ghsa}, {advisory['severity']}, "
                f"{advisory['title']}{note}"
            )
    return [findings[ghsa] for ghsa in sorted(findings)]


def main(argv: list[str]) -> int:
    """Print the blocking advisories and return 1, or return 0 when there are none."""
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    exceptions = read_exceptions(Path(argv[1]).read_text(encoding="utf-8"))
    findings = blocking_findings(report, exceptions, datetime.now(UTC).date())
    for finding in findings:
        print(finding)
    if not findings:
        print(f"No blocking advisories ({len(exceptions)} accepted with an expiry date).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
