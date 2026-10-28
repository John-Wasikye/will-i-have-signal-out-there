# Changelog: Platform

## Oct 28, 2026: incident records live in S3 and can be closed

- Each incident is filed in the lake as soon as it opens, numbered from what the lake already holds, and an upload never replaces a record the lake has (ADR-0024 update).
- A command closes a record with its cause and fix (operations, section 2).
- The nightly DAG allows one active run, and a fresh install starts it unpaused (pull request 14).
- A spot warning no longer records an incident. It sends the stop email, and the email plus the watchdog's log are the note that runbook PRB-3 asks for. Only the 2-hour maximum records an incident.

## Oct 22, 2026: Parameter Store check

- OQ-P10 answered: the Parameter Store path check is built with the platform skeleton. The paths are listed in `checks/parameter_paths.yaml`, CI checks them against the naming convention and the code, and the pull request plan checks that each listed parameter exists.

## Oct 9, 2026: defaults confirmed

- John confirmed ADR-0012 (10:00 UTC nightly start), ADR-0019 (30-day raw-file lock) and ADR-0032 (SHA-256 content hashes). Their status is now Accepted.

## Rev 2, Oct 9, 2026 (John's approvals)

- OQ-P01 approved: the SNS email and the Iceberg metrics table (ADR-0024), and SHA-256 for content hashes (ADR-0032). Both are now Accepted.
- OQ-P02 partly approved: the 4-hour session limit and the 2-hour nightly maximum are approved as written. The idle-alarm duration is still open, to be set from the first test run.

## Rev 1, Oct 9, 2026

Scope: shared by all five projects (Projects 1 to 5).

First full draft of the platform document set, written before any platform coding, as the Documentation Plan requires.

### Added

- README, requirements (skeleton steps 0.1 to 0.5, operations hardening 1B.9, the sixteen engineering standards, quality requirements and acceptance checks), and the 17-section design doc.
- Platform decision records 0001 to 0017, recorded from John's Oct 9 decisions in Build Plan Decisions. ADR-0024 (monitoring defaults) and ADR-0032 (SHA-256 hashes) are Defaults for John's approval.
- Shared contracts: platform_run_metrics, platform_incidents and status_json (ODCS v3.0.2).
- openapi-serving-template.yaml: the API spec each project copies (health and sample routes).

### Open for John

- OQ-P01: approve the defaults in ADR-0024 (SNS email, metrics table in the lake) and ADR-0032 (SHA-256).
- OQ-P02: approve the session limits and measure the idle-alarm duration.
- Spikes: OQ-P03 (ARM Marquez build), OQ-P04 (memory on the 32 GB box).
- Decisions: OQ-P05 to OQ-P10 (preview deploys, backups, Iceberg retention, freshness rule, API throttles, Parameter Store check).

### Not yet written (while building)

- Reference from code, operations and runbooks, security and privacy, licence register, and the platform model card (second round).

## Oct 9, 2026: decision records consolidated, references corrected, PDF built

- One set of 32 numbered decision records (0001 to 0032) is the set of record. The 17 older records were kept in `adrs/_superseded/` until Oct 9, 2026, when they were removed as duplicate old versions. Their content is covered by the numbered set.
- New records: 0031 (container images on ARM) and 0032 (SHA-256 for content hashes, a default).
- Corrected against the build plan and the Project 1 decisions: the assistant's monthly limit is $10 (Project 1 ADR 0038; the build plan's $15 is superseded); OQ-P numbers now match the design doc; references to other projects' records and to archived logs were removed; contract names now match the files.
- Citations in the design doc, requirements and this changelog were moved to the new record numbers.
- `contracts/usage_events.yaml` (the shared event format) is a draft for John's approval. The duplicate `metrics_table.yaml` was in `contracts/_superseded/` and was removed as an old version; `platform_run_metrics.yaml` is the metrics table.
- The platform PDF is built: `full-documentation.pdf` (71 pages). It was named `Platform - full documentation.pdf` until the PDFs were moved into each project's folder.
- Decided: `contracts/llm_calls.yaml` is the one call-log table for every project. It gains the X-Ray `trace_id`, and questions are stored only as a keyed HMAC. Project 1's older copy was in `Will I have signal out there/contracts/_superseded/` and was removed as an old version.
- Decided: the usage-event field list is accepted as drafted. The session gap is 30 minutes, and events are deleted after 90 days (ADR 0025).
