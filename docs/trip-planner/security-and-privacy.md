# Project 1 security and privacy

| Field | Value |
|---|---|
| Status | Draft for review. Residual risks are accepted by John when he approves this document |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Related | [design-doc.md](design-doc.md) (sections 3.5, 12.1 and 12.2), [../Platform/platform-requirements.md](../platform/platform-requirements.md) (sections 3, 9), [operations.md](operations.md), [model-card.md](model-card.md) |

This document covers three things: what could go wrong (the threat model), what personal data the project holds and for how long (the inventory), and where each licensed dataset comes from and what it requires (the register). Each control named here is either a recorded decision (cited as an ADR), a rule in the design doc, or a proposal marked as one.

---

## 1. Principles

1. **Exact locations never leave the phone.** A report carries only an H3 resolution 9 cell (about 350 m across), a carrier, a yes or no for signal, and the time rounded to the hour (ADR 0009).
2. **No identity from the network.** Limits use a random ID created on the phone. Internet addresses are not used for identity or limits (ADR 0011). They are removed from logs (ADR 0023).
3. **Data that is no longer needed is deleted on a fixed schedule.** Raw reports in DynamoDB are deleted 30 days after the nightly copy, and point-in-time recovery is off for that table so the deletion is final (ADR 0012, ADR 0022).
4. **Source text is data, never instructions.** Trail names, satellite names and user questions never change what the system does (design doc, section 12.1).
5. **Least privilege everywhere.** One role per pipeline, read-only roles for agents, and dev cannot write live data (platform step 0.2).
6. **Every key is in Parameter Store.** None is in code or GitHub (platform section 9).
7. **Nothing can run up a bill.** Every paid item has a hard limit (design doc, section 3.3).

## 2. What the system touches

```
Hiker's phone ──(cell, carrier, signal, hour; no ID in the body)──> Report API (Lambda)
       │                                                                  │
       │ random visitor ID (header)                                        ├──> DynamoDB: reports (no ID)
       └──────────────────────────────────────────────────────────────────>│──> DynamoDB: counters (ID, expires)
                                                                          │
Visitor's browser ──> CloudFront and Lambda ──> published Parquet (no personal data)
                       │
                       └── access logs (addresses removed; header excluded: proposed)

Nightly run: DynamoDB reports ──copy──> lake (Iceberg) ──> Snowflake (marts)
Assistant (Phase B): question ──> model API provider (external) ──> answer; call log in S3 (no question text)
```

## 3. Personal data inventory

| Data | Where it lives | Who can read it | Retention | Basis |
|---|---|---|---|---|
| Exact GPS position | The hiker's phone, in memory, for a moment | The hiker's phone only | Discarded once the cell is computed. Never sent | ADR 0009 |
| Report: H3 cell, carrier, signal yes or no, hour rounded to the hour | DynamoDB `signal_reports` (Phase B) | The report API (write); the nightly copy (read) | Deleted 30 days after the nightly copy | ADR 0012, ADR 0022 |
| Report copy in the lake and in Snowflake (Phase B) | Iceberg `signal_report`; Snowflake marts | Pipeline roles and Snowflake roles | Deleted 30 days after the copy; daily counts kept (OQ-43, ADR 0034) | Resolved, see section 8 |
| Set-aside reports (Phase B) | Iceberg `signal_report_set_aside` | John and pipeline roles, for review | Deleted 30 days after the copy (OQ-43, ADR 0034) | Resolved, see section 8 |
| Random visitor ID | The phone's local storage. Sent in the `X-Visitor-Id` header of `POST /reports`. Stored in `report_limit_counters` only | The report API; the counters table | Stored as an HMAC of the ID. Expires 72 hours after the UTC day (ADR 0025, ADR 0026) | ADR 0011 |
| System-wide daily counter | DynamoDB counters table, with no visitor ID | The report API | Expires | ADR 0011 |
| Internet addresses | CloudFront and API Gateway access logs | Platform logging only | Removed before storage. Kept 7 days (OQ-29, ADR 0029) | ADR 0023 |
| Votes (thumbs up or down) (Phase B) | DynamoDB `feedback_votes` | The vote API (write); John | 90 days, then deleted. No visitor ID (ADR 0033) | Build plan 1B.7 |
| Assistant question text (Phase B) | Sent to the model API provider. Not stored in the call log | The provider, under its own terms | The provider's retention follows its own terms, recorded before the first call (OQ-39, ADR 0034) | Contract `llm_call_log` |
| Assistant call log (Phase B) | S3, then Iceberg `llm_calls`: model, prompt version, tokens, latency, cost | Pipeline roles; John | Not yet decided. The clean-up rules do not name this log (confirm before Phase B) | Build plan 1B.5 |
| Email addresses | Not collected by this project | Not applicable | Not applicable | Design doc, section 3.5 |

### What is deliberately not stored

- Exact coordinates, on the phone or on the server.
- A visitor ID in any report record or in any table with a report.
- Internet addresses for identity or limits.
- Email addresses.
- Question text in the call log (the contract lists the field set; any change needs a decision, OQ-39).

## 4. Threat model

Each threat has a control, a way the control is checked, and a residual risk. A residual risk is what remains after the controls. John reviews each one when he approves this document.

| # | Threat | What it affects | Controls | How the control is checked | Residual risk |
|---|---|---|---|---|---|
| T1 | Exact location is sent to the server | Hiker privacy | The phone computes the H3 cell and discards the coordinates. The payload holds only the cell, carrier, signal and hour (ADR 0009) | Request-capture test (AC-1B.8, QR-10) | Low. A cell about 350 m across still shows the area |
| T2 | A report is linked to a hiker across reports | Hiker privacy | Reports carry no ID. Counters are apart from reports. Times are rounded to the hour. Raw rows are deleted 30 days after copy (ADR 0011, 0012) | DynamoDB inspection; expiry test (QR-11) | Medium. Two reports from the same small area in the same hour can point to one visit, although no ID links them |
| T3 | A visitor ID is linked to reports through access logs | Hiker privacy | Counters hold the ID, not reports. Internet addresses are removed (ADR 0023). **Proposed:** access logs exclude the `X-Visitor-Id` header and the report body | Log configuration review. The proposed exclusion is not yet built | Medium until the proposed exclusion is built and reviewed |
| T4 | A visitor clears storage to get a new ID and send more reports | Report integrity | Per-ID limits, plus the system-wide cap of 50 a day (ADR 0011). Set-aside step (ADR 0012) | Limit tests (AC-1B.8, section 13.1 of the design doc) | Medium. The system cap bounds the total, but one person can use up part of it |
| T5 | Fake or flood reports distort labels and counts | Model and page accuracy | One report per cell per visitor every 24 hours. Labels only where N reports in one cell on one day agree (ADR 0008; N open, OQ-12). Set-aside. System cap | Fixtures in the nightly copy tests (C23); runbook RB-14 | Medium. Low-volume fake reports within the limits remain possible |
| T6 | A stale prediction is shown as current | Hiker safety | `valid_until_utc` and the late notice. The last good run time is shown. Old data is never hidden (ADR 0006) | Front-end test with a controlled clock (QR-3, AC-1A.6) | Low. A wrong device clock changes what the page thinks is late |
| T7 | A key leaks (AWS, model API, Snowflake, Databricks) | All systems | Parameter Store only. OIDC for CI, so no AWS keys in GitHub. gitleaks and Trivy in CI. Least privilege | CI scans; role refusal test (QR-13) | Low to medium. A key pasted into a commit is exposed until it is rotated |
| T8 | Instructions hidden in source text or in a user question change the assistant's behavior | Assistant integrity | Source text is data. Metric tools come from a fixed allowlist. Raw SQL is read-only, allowlisted and logged. No write tool. Structured output | Red-team set of 20 or more prompts in CI (FR-47, AC-1B.7) | Medium. No model is immune. Its effect is limited to what it can read and answer |
| T9 | The assistant is used to run up model costs | Cost | $10 monthly spend limit set before the first call. Daily question cap. Token limit per answer. Cheapest model only (FR-42) | Limits set in the account; cost review (QR-9) | Low to medium. A burst inside one day can use up to the cap |
| T10 | Dev code writes to live data | Live data | Separate buckets, Glue databases and roles. Dev roles cannot write live (platform step 0.2) | Refusal test in Terraform checks | Low |
| T11 | A bad write to the reports table is lost | Report integrity | The lake copy is the only other copy. Point-in-time recovery is off by decision (ADR 0022) | None beyond the nightly copy | Accepted by John (ADR 0022). A bad write cannot be rolled back |
| T12 | Licensed data is published without its required notice | Licence compliance | Exact Ookla notice on the page and in the README (AC-1B.1). Credits for every source. License register (section 6) | Page text test; pull request checklist (QR-12) | Low. Credit wording for CelesTrak, FCC, NPS, Copernicus and OpenCelliD is still to confirm (OQ-22) |
| T13 | A source changes format and bad data is published | Data accuracy | Contract diff before loading (C8). Great Expectations gate (C9). Publish stops on failure (QR-4) | Tests on sample files in CI | Low |
| T14 | A compromised image or library reaches production | All systems | Trivy scans. Image manifests are checked before first use. The ARM Marquez build is pinned to one version | CI scans | Medium. Dependencies change often |
| T15 | Someone else gets into John's AWS account | All systems | Least privilege. Budget action. Session limit and idle shutdown limit exposure | **Not recorded:** whether MFA is on for the root and admin accounts. John confirms this before the first deploy | Not assessed until confirmed |
| T16 | Small-area counts reveal one person's report | Hiker privacy | Counts are per area. Area is H3 resolution 6; minimum 5 reports (ADR 0030) | Review of the area definition | Medium until a minimum count is set (OQ-35) |

## 5. Access

| Who or what | Can read | Can write | Notes |
|---|---|---|---|
| John | All `dev` data; `live` data through the console and Terraform | Terraform applies after approval; Parameter Store | Account access uses MFA (to confirm, T15) |
| CI (GitHub Actions, through OIDC) | Terraform state; sample files in CI | Plan on pull requests; apply after approval; dev deploys | Stores no AWS keys |
| Each pipeline role | Its own raw source; its tables in its environment | Its own raw source; its tables in its environment | One role per pipeline. Dev roles cannot write live |
| Serving Lambda | The published Parquet prefix only | Nothing | Reads only what the page needs |
| Report Lambda (Phase B) | Nothing in the lake | `signal_reports` and `report_limit_counters` | No read of the lake |
| Nightly copy role (Phase B) | `signal_reports` | The lake; the expiry attribute on copied rows | Sets expiry only after a successful copy |
| Assistant Lambda (Phase B) | Published tables; metric tools on the allowlist; read-only SQL on allowlisted views | The call log in S3 | No write tool (ADR 0017) |
| Vote endpoint (Phase B) | Nothing | `feedback_votes` | Runs behind API Gateway like the other endpoints |
| Hiker's phone | Its own queue | Sends reports to the report API only | Holds the visitor ID and the queue |

Exact policies are written in Terraform, in the platform repository. This table is the requirement they must meet.

## 6. Licence and attribution register

| Source | Terms | What is published from it | What must appear | Status |
|---|---|---|---|---|
| Ookla open data | CC BY-NC-SA 4.0. Non-commercial. Derived data is shared under the same licence | Speed tiles, confidence values (Phase B) | The exact notice: "Includes data derived from Speedtest by Ookla® open data, licensed under CC BY-NC-SA 4.0. Derived data published here is shared under the same license." On the page and in the README (ADR 0013, AC-1B.1) | Required from Phase B |
| OpenCelliD | Share-alike, CC BY-SA 4.0 according to secondary sources. Primary page not readable (HTTP 403) | Confidence values that use tower distance (ADR 0024) | Cell tower locations: OpenCelliD (opencellid.org), licensed CC BY-SA 4.0 | Unverified: read the OpenCelliD terms before publishing (ADR 0037) |
| Copernicus GLO-30 elevation | Free of charge under the Copernicus DEM licence (read from the licence text) | Horizons (derived, so the modified-data notice applies) | "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved." Plus the liability statement when distributed | Verified (ADR 0037) |
| TIGER/Line roads (U.S. Census Bureau) | Declared CC0 (public domain) on data.gov. Some files carry a rights flag, "otherRestrictions"; check the Census page for the exact vintage before the first load | Derived distances only; road geometry is kept only if the check allows it | Credit the Census Bureau on the page. Check the flag (first-run check, ADR 0035) | Phase B |
| NPS Public Trails | Public domain under NPS policy; credit appreciated, not required | Trail lines, trail points, horizons | Trail data: National Park Service | Verified (ADR 0037) |
| CelesTrak | No terms found; courtesy credit | Satellite windows (derived, not raw sets) | Orbital data: CelesTrak (celestrak.org), maintained by Dr. T.S. Kelso | Courtesy credit. Ask the maintainer before republishing raw sets (ADR 0037) |
| FCC mobile coverage | Courtesy credit per secondary sources; carrier submissions may carry restrictions. Primary page not readable (HTTP 403) | Coverage flags, confidence values | Coverage data: FCC National Broadband Map (broadbandmap.fcc.gov) | Unverified: check before Phase B publishes carrier data (ADR 0037) |
| Databricks Free Edition | Service terms, non-commercial | Nothing published. Model copy in the repo is derived from training | Licensing is checked before any charge (design doc, section 3.4) | Phase B |
| Model API provider | Anthropic API (ADR 0034). Terms to record before the first call | Nothing published. Questions are sent to it | Recorded before the first call (OQ-39) | Phase B; open |
| Open-source libraries (for example h3-js, FastAPI, DuckDB) | Their own licences | Code | Licence text recorded in the repository when each library is added | Ongoing |

The project is non-commercial. Licensing is checked before charging for any of it (design doc, section 3.4).

## 7. Logs and retention

| Log or record | Kept | Deleted | Notes |
|---|---|---|---|
| Pipeline logs | 90 days | Yes, after 90 days | Clean-up rule |
| Security logs (CloudTrail, Parameter Store reads) | 1 year | Yes, after 1 year | Matches the PCI convention noted in the Build Plan Decisions |
| Access logs (CloudFront, API Gateway) | 7 days | Addresses are removed before storage (ADR 0023) | Deleted after 7 days (ADR 0029) |
| Report rows in DynamoDB | Until 30 days after copy | Yes | ADR 0012 |
| Report copy in the lake and Snowflake | 30 days after the copy | Yes | ADR 0034 |
| Counters | 72 hours after the UTC day | Yes | ADR 0026 |
| X-Ray traces | Per the X-Ray setting | Per the X-Ray setting | Traces hold agent runs. Their retention is not recorded; confirm before Phase B |

## 8. Gaps this review found

These are places where the documents did not yet protect a privacy promise. Each is recorded so that John decides it.

1. **Resolved (ADR 0034): the lake and Snowflake copies of reports now follow the 30-day rule.** Before this decision they had no rule. The 30-day rule covers only the DynamoDB rows. Without a rule, the copies in the lake and Snowflake would be kept under the general "raw and published data kept" rule. Decision: OQ-43.
2. **Access logs could record the visitor ID.** The visitor ID travels in a header of `POST /reports`. Without an exclusion, an access log could link it to a report. Proposed control: exclude the header and the report body from logs (design doc, section 12.2). Decision: approve with the design doc (OQ-21).
3. **Assistant questions go to an outside provider.** A question can contain personal detail, such as who is hiking with the visitor. The call log does not store question text, but the provider receives it, and its terms are not recorded. Decision: OQ-39.
4. **Small counts can identify one person.** A count of one report for an area and hour can show one person's visit. Decided: counts are shown only from 5 reports, in an H3 resolution 6 area (ADR 0030).
5. **MFA is not recorded for John's AWS accounts.** Confirm before the first deploy (T15).

## 9. Incidents involving privacy

Privacy incidents follow the process in [operations.md](operations.md), section 5. The response is:

1. Stop the copy or the publish that causes it.
2. Delete the affected rows or files. Deletion of DynamoDB rows is final, so confirm the scope before deleting.
3. Record what was exposed, for how long, and to whom.
4. Change the control, or record why the risk is accepted, before the next run.

## 10. Open items

| Item | Where it is tracked |
|---|---|
| Model provider's terms and question retention | OQ-39 |
| Verify OpenCelliD terms, FCC mobile-data terms and the Census rights flag before publishing | ADR 0037 |
| Approval of the log exclusion for the visitor ID header | OQ-21 (with the design doc) |
| MFA on John's AWS accounts | Confirm before the first deploy |
| Retention of X-Ray traces | Confirm before Phase B |
