# Project 1 operations

| Field | Value |
|---|---|
| Status | Draft for review. Written before coding so the failure handling is designed in. Numbers from measured runs replace the estimates in section 7 when the first runs exist |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Related | [design-doc.md](design-doc.md) (sections 8, 12 and 13), [../Platform/platform-requirements.md](../platform/platform-requirements.md), [security-and-privacy.md](security-and-privacy.md) |

This document says how the project runs day to day: when things happen, what is watched, what a person does when something breaks, and what the project costs. It is written to be followed by someone who did not build the system.

---

## 1. Schedule

| Job | When | Where it runs | Maximum run time |
|---|---|---|---|
| Nightly pipeline run (C1 to C10, plus Iceberg maintenance last) | Every day at 10:00 UTC (3 a.m. Arizona, 6 a.m. US Eastern) | Session box, spot only | 2 hours. Usually about 45 minutes |
| Orbit element pull (C1) | At most once per 2-hour update, inside the nightly run | Session box | Stops on any response other than HTTP 200 |
| Nightly report copy (C23, Phase B) | Inside the nightly run | Session box, reading DynamoDB | Part of the 2-hour maximum |
| Kafka orbit stream (C14, Phase B) | Inside the nightly run, with availableNow | Session box | Part of the 2-hour maximum |
| Snowflake refresh (C15, Phase B) | After each pipeline run | Snowflake | Query time limit on every query |
| Weekly source smoke test (C24, Phase B) | Once a week | GitHub Actions or the box (platform decision) | Not recorded |
| Databricks keep-alive (Phase B) | Once a month | Databricks Free Edition | Not recorded |
| Model retrain and export (Phase B) | After a training run, by hand | John's computer and Databricks | Not recorded |

Hitting the 2-hour maximum is recorded as an incident. The next run catches up.

## 2. Freshness targets

A freshness target is the longest time a published dataset may be out of date before it is treated as late.

| Published data | Target | What the page shows when the target is missed |
|---|---|---|
| Satellite windows (`fct_satellite_window`) | Published every night, inside the 2-hour maximum. Each run predicts 26 hours, so the previous run is still valid when the next one publishes (ADR 0019) | Old data with a late notice and the time of the last good run (ADR 0006) |
| Trail coverage (`fct_trail_point_coverage`) | Rebuilt every night. The FCC input changes only with a new release | Same as above |
| Trail points and horizons (`dim_trail_point`, `trail_point_horizon`) | Reference data. Recomputed when the inputs change, or nightly if OQ-25 decides so | Same as above |
| Confidence values (`fct_coverage_confidence`, Phase B) | Scored every night with the model copy in the repo | Same as above |
| Report counts (`fct_report_counts_area`, Phase B) | Nightly, from the copy of reports | Same as above |

"Late" is defined in ADR 0027 (OQ-23). A trail's data is late when the current time is past its validity time, or when the most recent scheduled run did not publish. The alerts use the same rule.

## 3. What is watched

| Signal | Where it is shown | Who is told |
|---|---|---|
| Freshness and row count for every pipeline run | Metrics table, written by every DAG (platform step 0.5) | Read on the status page |
| Each pipeline's last good run | `status.json`, read by the status page | Read on the status page |
| A failed run or a missed freshness target | Email through Amazon SNS (proposed, OQ-21) | John, by email |
| A failed run or missed target (Phase B) | One GitHub issue. Duplicates are merged into it. It closes when the pipeline recovers | John, in GitHub |
| Storage size passes a set level | CloudWatch alarm on the lake bucket. Level is open (OQ-15) | John, by email |
| Session box idle | CloudWatch alarm stops the box | Logged; no email unless the box fails to stop |
| Session limit (4 hours) | The box is stopped by the limit | Logged |
| Spend | AWS Budget at $40 with an action (backup); Snowflake resource monitor at 3 credits; Model API limit at $10 a month and a daily question cap | Budget email; resource monitor suspends the warehouse |
| Model calls (Phase B) | Call log in S3, loaded nightly into `llm_calls`; traces in AWS X-Ray | Grafana reads X-Ray during work sessions |
| Cold-start time (Phase B) | Measured, reported as median warm latency and 95th-percentile cold-start time in the README | Read in the README |
| Source format changes (Phase B) | Weekly smoke test pulls one small sample from every source and alerts on a format change | Email and GitHub issue |

## 4. Cost

Estimates are from public price pages as of Oct 8, 2026. They are rechecked before the first run and after every change of instance type.

| Item | Spot | On-demand | Hard limit |
|---|---|---|---|
| Session box, `t4g.2xlarge`, about 70 hours a month | $5.40 to $9.70 | $18.82 | 4-hour session limit; idle shutdown |
| Heavy batch on `m7g.2xlarge`, about 30 hours a month | $4.80 to $6.20 | $9.79 | Same limits |
| Disk, 50 GB gp3 while running | $0.55 | $0.55 | Disk size fixed in Terraform |
| S3 storage, up to about 150 GB by Phase C (far less early on) | Up to $3.45 | Up to $3.45 | Clean-up rules (section 6); size alarm |
| Fargate ingest tasks | About $1 | About $1 | Fixed schedule |
| Public IPv4 while running | $0.50 | $0.50 | Only while the box runs |
| Nightly pipeline run, about 22 hours a month | $2 to $3.35 | $2 to $3.35 | Always spot; 2-hour maximum |
| AWS total | $18 to $25 | About $37 | $40 AWS budget as backup |
| Snowflake after the trial | Up to $6 | Up to $6 | 3 credits a month; query time limit |
| Model API, cheapest model only | $5 to $10 | $5 | $10 a month spend limit; daily question cap; token limit per answer |
| All in, normal month | About $23 to $46 | About $45 to $48 | Under $50 a month |

The skeleton and Phase A months are usually under $20, because they need few box hours and no warehouse.

Each Spark job also has a limit on rows read and written and on runtime. A job over either limit stops before publishing and opens an incident. The values are open until measured (OQ-1 and OQ-15).

## 5. Incidents

An incident record is written for every real failure. A short record is enough for a small failure. A blameless postmortem is written for each real incident.

Record fields:

- **ID and date**, and the pipeline or component that failed
- **Detected by**: the alarm, the email, the status page or a person
- **What visitors saw**: the page as it was, including any late notice
- **Cause**
- **Fix**
- **Follow-up**: a change to a runbook, a contract, a limit or a design decision, with its own record
- **Runbook updated**: yes or no

Blameless means the record asks what allowed the failure, not who caused it.

## 6. Runbooks

Each runbook names the symptom, how it is detected, what the visitor sees, the first action, the fix, and what to record. Every failure here leaves the previously published data live, so a failed run is never shown as a new result.

### RB-1: CelesTrak returns a status other than 200

- **Detected by:** the orbit ingest DAG (C1) stops and the run fails.
- **Visitor sees:** the previous satellite windows, with the late notice once their `valid_until_utc` passes.
- **First action:** check the CelesTrak status and the URL in the contract (OQ-20).
- **Fix:** none needed for a short outage. The next run retries. If the URL moved, update the contract through a reviewed change.
- **Record:** an incident if the outage lasts past one nightly run.

### RB-2: Schema diff fails (C8)

- **Detected by:** the schema diff compares the new file with the contract and stops the run before anything loads.
- **Visitor sees:** the previous data, with the late notice once it is late.
- **First action:** read the diff. It names each added, removed or changed field.
- **Fix:** if the source changed on purpose, update the contract, rerun the tests with the new sample, and then rerun the pipeline. If not, report it to the source.
- **Record:** an incident, with the diff.

### RB-3: The DTC cross-check lists disagreements (C2)

- **Detected by:** the selector lists satellites whose altitude or inclination disagrees with the `[DTC]` tag.
- **Visitor sees:** nothing new. The run does not fail on disagreements (design doc, section 8.1).
- **First action:** read the list. Decide whether the tag or the cross-check is wrong for each satellite.
- **Fix:** record the decision in an ADR. Change the selector only with a test that shows the change.
- **Record:** the list and the decision.

### RB-4: A job exceeds its row or runtime limit (C5)

- **Detected by:** `enforce_row_limit` stops the satellite window job before publishing.
- **Visitor sees:** the previous data, with the late notice once it is late.
- **First action:** read the row count and runtime from the metrics table. Compare them with the size estimate in the design doc.
- **Fix:** if the estimate was wrong, record the measured figures and set the limit from them (OQ-1, OQ-15). Do not raise a limit to get past a failure without a recorded reason.
- **Record:** an incident with the measured figures.

### RB-5: A dbt test fails (C7)

- **Detected by:** dbt test failure stops the run before the publish gate.
- **Visitor sees:** the previous data, with the late notice once it is late.
- **First action:** read the failing test name and its model.
- **Fix:** fix the model or the input. A test is never removed to get a run through; a change to a test is recorded in an ADR.
- **Record:** an incident.

### RB-6: The publish gate fails (C9)

- **Detected by:** a Great Expectations check fails (freshness, empty results or value ranges). Publishing stops, and the previously published Parquet stays live.
- **Visitor sees:** the previous data, with the late notice once it is late.
- **First action:** read the failed expectation.
- **Fix:** if the source is at fault, hold the publish until the source is fixed. If the expectation is wrong, change it through a recorded decision.
- **Record:** an incident.

### RB-7: The nightly run reaches the 2-hour maximum

- **Detected by:** the session box stops at the maximum. The run is marked incomplete.
- **Visitor sees:** the previous data. The next night's run catches up.
- **First action:** read the metrics table to see which step took the time.
- **Fix:** move the slow step out of the nightly run if it can run in a work session (backfills always run in sessions). Otherwise, change the step.
- **Record:** an incident with the step and its time.

### RB-8: Spot capacity is unavailable at 10:00 UTC

- **Detected by:** the box does not start. The night is recorded as skipped.
- **Visitor sees:** the previous data, with the late notice once it is late.
- **First action:** none. The next run catches up.
- **Fix:** if spot is unavailable for several nights, reconsider the instance choice in the design doc. The build plan makes the nightly run spot only, so switching it to on-demand needs a recorded decision and a new cost check.
- **Record:** a note in the metrics table. An incident if two nights in a row are skipped.

### RB-9: A spot server is taken back mid-run

- **Detected by:** the interruption handler records the two-minute warning and the run stops.
- **Visitor sees:** the previous data.
- **First action:** rerun the nightly pipeline on a new box.
- **Fix:** none. Every job overwrites its own partition, so a rerun replaces only that day.
- **Record:** a note in the metrics table.

### RB-10: Airflow's saved database cannot be restored

- **Detected by:** the box starts without its run history.
- **Visitor sees:** nothing new. Pipelines can run from the start.
- **First action:** start the pipelines from the beginning. Every task is safe to rerun.
- **Fix:** check the S3 copy and the restore step. Keys come from Parameter Store, so the saved copy holds none.
- **Record:** an incident.

### RB-11: Databricks is unavailable or its free account lapsed (Phase B)

- **Detected by:** training or export fails. The nightly scoring does not use Databricks, so it is unaffected.
- **Visitor sees:** nothing new. The page uses the model copy in the repo.
- **First action:** check the Databricks account and its quota.
- **Fix:** if the account lapsed, the monthly keep-alive job has failed. Restore the account and run the keep-alive. Training waits.
- **Record:** a note. An incident only if the copy in the repo is out of date.

### RB-12: Snowflake does not see new data after the refresh (Phase B)

- **Detected by:** the refresh step shows no new rows, or a metric differs between Snowflake and DuckDB.
- **Visitor sees:** nothing. The site does not read Snowflake (ADR 0015).
- **First action:** check the Glue connection and the refresh command.
- **Fix:** rerun the refresh after the pipeline has finished. If the connection fails, see OQ-4.
- **Record:** an incident if a metric is wrong.

### RB-13: The report copy fails (C23, Phase B)

- **Detected by:** the copy stops before setting any expiry.
- **Visitor sees:** nothing. No report is deleted before it is copied (ADR 0012).
- **First action:** rerun the copy. It is safe to rerun.
- **Fix:** read the failing step.
- **Record:** an incident if the copy has failed for more than one night.

### RB-14: A flood or fake reports arrive (Phase B)

- **Detected by:** the per-day counts in `fct_report_counts_area` jump, or the set-aside table fills.
- **Visitor sees:** counts that may be wrong until the set-aside step catches the pattern.
- **First action:** read the set-aside rows (`signal_report_set_aside`).
- **Fix:** tighten a limit only with a recorded decision. The system-wide cap of 50 a day stops floods at the write step.
- **Record:** an incident with the pattern.

### RB-15: The assistant's spend or question count rises (Phase B)

- **Detected by:** the daily question cap refuses questions, or the model API spend nears $10 in a month.
- **Visitor sees:** the assistant refuses questions over the cap, with the `assistant_limit_exceeded` error.
- **First action:** read `llm_calls` for the calls and their prompt versions.
- **Fix:** if the traffic is abusive, leave the cap in place. If it is real use, raise the cap by a recorded decision.
- **Record:** an incident.

### RB-16: A source changes its format (weekly smoke test, Phase B)

- **Detected by:** the weekly smoke test finds a format change before the nightly run fails.
- **Visitor sees:** nothing yet.
- **First action:** read the change.
- **Fix:** update the contract and its tests, through a reviewed change, before the next nightly run.
- **Record:** an incident and a changelog line.

### RB-17: The page shows the late notice when it should not

- **Detected by:** a visitor or John sees a late notice on fresh data.
- **Visitor sees:** a notice that is wrong about freshness.
- **First action:** compare the device clock with UTC. The page compares `valid_until_utc` with the browser clock (ADR 0006), so a wrong device clock changes the result.
- **Fix:** if the clock was right, check `last_good_run_utc` and the status page.
- **Record:** an incident if the data itself was stale.

## 7. Backups and recovery

| What | Backup | Recovery |
|---|---|---|
| Raw source files | Never changed. Live raw files are locked for 30 days | Re-download from the source, or from the raw file |
| Lake tables (Iceberg) | Snapshots and the raw files they came from | Rerun the affected day. Each day's partition is replaced |
| Published Parquet | The previous publish stays until the next one passes | The previous publish stays live |
| Airflow's database | Saved to S3 after every run and at shutdown | Restored at startup. If lost, the pipelines run again |
| Reports (DynamoDB, Phase B) | Point-in-time recovery is off for this table, so deletion is final at 30 days (ADR 0022). The lake copy is the only other copy | A bad write cannot be undone from DynamoDB; the lake copy is the recovery source |
| Visitor votes (Phase B) | Point-in-time recovery is on | Restore to an earlier point in time |
| Visitor counters (Phase B) | Point-in-time recovery off (OQ-41, ADR 0025) | Not recoverable by design. Counters expire 72 hours after their UTC day (ADR 0026) |
| Terraform state | Versioned S3 bucket | Restore an earlier version |

## 8. Clean-up and retention

| Data | Rule |
|---|---|
| Dev data | Deleted after 14 days |
| Temporary files and Spark checkpoints | Deleted after 7 days |
| Failed partial uploads | Deleted after 7 days |
| Pipeline logs | Deleted after 90 days |
| Security logs (CloudTrail, including Parameter Store reads) | Kept 1 year |
| Old file versions | Deleted after 30 days |
| Raw source files and published data | Kept |
| Raw report rows in DynamoDB (Phase B) | Deleted 30 days after the nightly copy |
| Lake and Snowflake copies of reports | Deleted 30 days after the copy. Daily per-cell counts are kept (OQ-43, ADR 0034) |
| Access log addresses (CloudFront and API Gateway) | Removed before storage. Kept 7 days, then deleted (OQ-29, ADR 0029) |

Iceberg maintenance (compact, expire snapshots, remove orphan files) runs as the last task of the nightly run so it never competes with the pipelines.

## 9. Routine maintenance

| Task | When |
|---|---|
| Review the open questions list and the issues for each one | Each time a spike answers a question |
| Check the cost against section 4 | Monthly |
| Check the weekly smoke test | Weekly (Phase B) |
| Keep the Databricks account active | Monthly (Phase B) |
| Check the budget, the resource monitor and the model API spend limit | Monthly |
| Review the incident records and close runbook gaps | Monthly |
| Recheck the Marquez ARM image | Only when an upgrade is chosen (Phase B) |

## 10. Access during operations

- John owns the system and is the only person with production access.
- Each pipeline runs under its own least-privilege role. Dev roles cannot write live data (platform step 0.2).
- Agents, from Phase B, have read-only access through an allowlist (design doc, section 12.1).
- Keys are read from Parameter Store only. Each read is logged through CloudTrail.

## 11. Open operational questions

| Question | Where it is tracked |
|---|---|
| Row and runtime limits; storage alarm size; freshness thresholds | OQ-1, OQ-15 |
| Whether the Databricks export can be automated | OQ-19 |
| Whether the platform stack fits 32 GB of memory | Design doc, section 16 |
