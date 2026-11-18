"""Tests for the site's package audit gate (CI job "Site lint, build and tests").

`npm audit` cannot skip one advisory, so the gate reads its JSON report and fails on every
advisory of moderate severity or worse, except those listed in `.github/npm-audit-exceptions.txt`.
Each exception has an expiry date, like `.trivyignore`, so the check fails again on that day and
I have to look again.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from npm_audit_gate import blocking_findings, main, read_exceptions  # noqa: E402

TODAY = date(2026, 11, 17)
PICOMATCH = {
    "source": 1117591,
    "name": "picomatch",
    "dependency": "picomatch",
    "title": "picomatch vulnerable to ReDoS through single-branch repeated extglobs",
    "url": "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
    "severity": "high",
    "range": "<=4.0.7",
}


def _report(*advisories, extra=None):
    """An npm audit --json report: one entry per package, `via` holding advisories or names."""
    vulnerabilities = {
        advisory["name"]: {
            "name": advisory["name"],
            "severity": advisory["severity"],
            "via": [advisory],
        }
        for advisory in advisories
    }
    vulnerabilities.update(extra or {})
    return {"auditReportVersion": 2, "vulnerabilities": vulnerabilities}


def _advisory(name, ghsa, severity):
    return PICOMATCH | {
        "name": name,
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": severity,
    }


def test_a_listed_advisory_before_its_expiry_does_not_block():
    exceptions = {"GHSA-fc5q-39xc-vjpf": date(2026, 12, 17)}

    assert blocking_findings(_report(PICOMATCH), exceptions, TODAY) == []


def test_a_listed_advisory_after_its_expiry_blocks():
    exceptions = {"GHSA-fc5q-39xc-vjpf": date(2026, 11, 16)}

    (finding,) = blocking_findings(_report(PICOMATCH), exceptions, TODAY)
    assert "GHSA-fc5q-39xc-vjpf" in finding
    assert "expired 2026-11-16" in finding


def test_an_unlisted_advisory_blocks():
    (finding,) = blocking_findings(_report(PICOMATCH), {}, TODAY)

    assert "picomatch" in finding
    assert "GHSA-fc5q-39xc-vjpf" in finding
    assert "high" in finding


def test_a_low_severity_advisory_does_not_block():
    """The old step used --audit-level=moderate, so low and info stay allowed."""
    low = _advisory("left-pad", "GHSA-aaaa-bbbb-cccc", "low")

    assert blocking_findings(_report(low), {}, TODAY) == []


def test_an_exception_covers_only_its_own_advisory():
    other = _advisory("braces", "GHSA-dddd-eeee-ffff", "moderate")
    exceptions = {"GHSA-fc5q-39xc-vjpf": date(2026, 12, 17)}

    (finding,) = blocking_findings(_report(PICOMATCH, other), exceptions, TODAY)
    assert "GHSA-dddd-eeee-ffff" in finding


def test_packages_that_only_depend_on_a_flagged_package_add_nothing():
    """npm lists every parent of a flagged package; only the advisory itself counts once."""
    parent = {"fdir": {"name": "fdir", "severity": "high", "via": ["picomatch"]}}

    assert len(blocking_findings(_report(PICOMATCH, extra=parent), {}, TODAY)) == 1


def test_an_audit_that_could_not_run_blocks():
    report = {"error": {"code": "ENOAUDIT", "summary": "the registry did not answer"}}

    (finding,) = blocking_findings(report, {}, TODAY)
    assert "did not run" in finding


def test_the_exception_list_reads_ids_and_expiry_dates_and_skips_comments():
    text = "# picomatch: reason here.\n\nGHSA-fc5q-39xc-vjpf exp:2026-12-17\n"

    assert read_exceptions(text) == {"GHSA-fc5q-39xc-vjpf": date(2026, 12, 17)}


def test_an_exception_without_an_expiry_date_is_refused():
    with pytest.raises(ValueError, match="exp:"):
        read_exceptions("GHSA-fc5q-39xc-vjpf\n")


def test_main_fails_on_a_blocking_finding_and_passes_without_one(tmp_path, capsys):
    report = tmp_path / "audit.json"
    report.write_text(json.dumps(_report(PICOMATCH)), encoding="utf-8")
    listed = tmp_path / "exceptions.txt"
    listed.write_text("GHSA-fc5q-39xc-vjpf exp:2099-01-01\n", encoding="utf-8")
    empty = tmp_path / "none.txt"
    empty.write_text("# nothing accepted\n", encoding="utf-8")

    assert main([str(report), str(empty)]) == 1
    assert "GHSA-fc5q-39xc-vjpf" in capsys.readouterr().out
    assert main([str(report), str(listed)]) == 0


def test_the_repository_exception_list_is_valid():
    path = Path(__file__).resolve().parents[1] / "npm-audit-exceptions.txt"

    exceptions = read_exceptions(path.read_text(encoding="utf-8"))
    assert all(expiry > date(2026, 11, 17) for expiry in exceptions.values())
