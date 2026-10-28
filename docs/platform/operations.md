# Platform operations

| Field | Value |
|---|---|
| Status | Draft for review. Shared by all five projects |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Related | [platform-requirements.md](platform-requirements.md) (sections 3 to 6), [design-doc.md](design-doc.md), [security.md](security-and-privacy.md) |

This document covers how the shared platform runs day to day: the nightly schedule, what is watched, the cost limits, and the runbooks for failures that hit every project. Each project's own runbooks are in that project's operations document.

---

## 1. Schedule

| Job | When | Where | Maximum |
|---|---|---|---|
| Nightly run (every project's pipelines, in order) | 10:00 UTC (3 a.m. Arizona, 6 a.m. US Eastern) | Session box, spot only | 2 hours. Usually about 45 minutes |
| Platform status file (`status.json`) | After each run | Written by the run, read by the status page | Part of the run |
| Iceberg maintenance (compact, expire snapshots, remove orphan files) | Last task of the nightly run | Session box | Part of the run |
| CI on every push | On every push | GitHub Actions, on GitHub's hosted machines | Not billed (public repository) |
| Terraform plan | On every pull request | GitHub Actions | Not billed |
| Terraform apply | After approval | GitHub Actions | Not billed |

Hitting the 2-hour maximum is recorded as an incident. The next run catches up.

## 2. Monitoring

| Signal | Where it is shown | Who is told |
|---|---|---|
| Freshness and row count for every pipeline run | The shared metrics table (`platform_run_metrics`, see `contracts/`) | Read on the status page |
| Each pipeline's last good run | `status.json` | Read on the status page |
| A failed run, or a missed freshness target | Email (Amazon SNS, proposed) | John |
| One GitHub issue per failure (from the first project in Phase B) | GitHub | John |
| Storage passes a set size | CloudWatch alarm | John |
| Session box idle | CloudWatch alarm stops the box | Logged |
| Session limit (4 hours) | The box stops | Logged |
| Spend | AWS Budget at $40, with an action that stops new launches (backup) | Budget email |

### Incident records

- **Where:** one Parquet file per incident in the lake bucket of each environment, under `platform/incidents/`, named by its ID (for example `INC-2026-10-27-01.parquet`). The records stay private, because the error text can name files and tables. The failure email is the notice; the file is the record.
- **Closing one:** once the cause and the fix are known, run from the repository root, after `pip install ".[ops]"` and an AWS sign-in:

  ```
  python pipelines/platform/publish/incidents.py close --bucket <lake bucket> --id <incident ID> --cause "<why it broke>" --fix "<what fixed it>"
  ```

  It refuses a record that is already closed, an empty cause or fix, and a record that changed while it was being closed. The bucket keeps the open version in its history.

## 3. Cost

Estimates are from public price pages as of Oct 8, 2026. They are checked before the first run and after any change of instance type. The project-level models in each project's operations document add their own costs.

| Item | Spot | On-demand | Limit |
|---|---|---|---|
| Session box, `t4g.2xlarge`, about 70 hours a month | $5.40 to $9.70 | $18.82 | 4-hour session limit; idle shutdown |
| Heavy batch on `m7g.2xlarge`, about 30 hours a month | $4.80 to $6.20 | $9.79 | Same limits |
| Disk, 50 GB gp3 while running | $0.55 | $0.55 | Fixed in Terraform |
| S3 storage | Up to $3.45 | Up to $3.45 | Clean-up rules (section 5) and a size alarm |
| Fargate ingest tasks | About $1 | About $1 | Fixed schedule |
| Public IPv4 while running | $0.50 | $0.50 | Only while the box runs |
| Nightly run, about 22 hours a month | $2 to $3.35 | $2 to $3.35 | Always spot; 2-hour maximum |
| AWS total | $18 to $25 | About $37 | $40 budget as backup |
| Snowflake after the trial | Up to $6 | Up to $6 | 3 credits a month; query time limit |

The cost of the model API is in the trip-planning project's own documents (Project 1, ADR 0038). Its limit is $10 a month.

## 4. Runbooks for platform failures

Each runbook names the symptom, how it is found, the first action, and what to record. A failed run never publishes its partial output, so visitors keep the last good data.

### PRB-1: The session box does not start at 10:00 UTC

- **Found by:** no run has started. The status page shows the night as skipped.
- **First action:** check spot capacity for the instance type. If spot is unavailable, the night is skipped and the next run catches up.
- **Fix:** if spot is unavailable several nights in a row, change the instance choice in the design doc. Switching to on-demand needs a recorded decision and a cost check, because the nightly run is spot only.
- **Record:** a note. An incident if two nights in a row are skipped.

### PRB-2: The box stops at the 2-hour maximum

- **Found by:** the box stops before the pipelines finish. The run is marked incomplete.
- **First action:** read the metrics table to find the step that took the time.
- **Fix:** move the slow step out of the nightly run if it can run in a work session. Backfills always run in sessions.
- **Record:** an incident with the step and its time.

### PRB-3: A spot server is taken back mid-run

- **Found by:** the watchdog reads AWS's two-minute warning, saves the database, emails me, and powers the box off. The run stops.
- **First action:** rerun on a new box. Every job overwrites its own partition, so a rerun replaces only that day.
- **Record:** a note, not an incident, because nothing broke. The note is the stop email ("AWS will stop the box at ...") and the watchdog's log on the box (`journalctl -u box-watchdog -b -1` after the next boot). The same applies to a spot warning during a work session.

### PRB-4: Airflow's saved database cannot be restored

- **Found by:** the box starts without its run history.
- **First action:** run the pipelines from the beginning. Every task is safe to rerun.
- **Fix:** check the copy in S3 and the restore step. The copy holds no keys, because keys come from Parameter Store.
- **Record:** an incident.

### PRB-5: A key is exposed (for example, pasted into a commit)

- **Found by:** gitleaks in CI, or someone who sees it.
- **First action:** rotate the key in its provider, and store the new value in Parameter Store.
- **Fix:** remove the value from the repository history, and check the access log in CloudTrail for uses of the old value.
- **Record:** an incident with the key name, the time it was exposed, and the time it was rotated.

### PRB-6: A deploy would change live data from dev

- **Found by:** the dev role is refused when it tries to write to a live bucket or database. The refusal is the expected result.
- **First action:** find out why a live target was in the dev configuration, and correct it.
- **Record:** an incident if the refusal was not raised by the role's policy.

### PRB-7: The budget action fires

- **Found by:** the $40 budget alert.
- **First action:** check which item spent the money, using the budget breakdown.
- **Fix:** stop the item. If it is the session box, the action has already stopped new launches.
- **Record:** an incident.

## 5. Clean-up and retention

| Data | Rule |
|---|---|
| Dev data | Deleted after 14 days |
| Temporary files and Spark checkpoints | Deleted after 7 days |
| Failed partial uploads | Deleted after 7 days |
| Pipeline logs | Deleted after 90 days |
| Security logs (CloudTrail, including Parameter Store reads) | Kept 1 year |
| Old file versions | Deleted after 30 days |
| Raw source files and published data | Kept |
| Live raw files | Locked against deletion or overwrite for 30 days |

## 6. Backups and recovery

| What | Backup | Recovery |
|---|---|---|
| Raw source files | Never changed; live files locked for 30 days | Re-download, or use the raw copy |
| Lake tables | Iceberg snapshots, plus the raw files they came from | Rerun the affected day |
| Published data | The previous publish stays until the next one passes | The previous publish stays live |
| Airflow's database | Saved to S3 after every run and at shutdown | Restore at startup, or rerun from the beginning |
| Terraform state | Versioned S3 bucket with locking | Restore an earlier version |
| Visitor tables (DynamoDB) | Point-in-time recovery on, except where a project turns it off by decision | Restore to an earlier point in time |

## 7. Routine checks

| Check | How often |
|---|---|
| Cost against section 3 | Monthly |
| Budget, Snowflake resource monitor and model-API limits | Monthly |
| Keys: rotation status and unused keys | Quarterly |
| Dev roles still refused on live targets | Each change to the roles |
| Runbooks against the last incidents | Monthly |
