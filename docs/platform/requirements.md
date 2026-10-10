# Platform: requirements

| Field | Value |
|---|---|
| Status | Draft, awaiting John's review and approval |
| Scope | Shared by all five projects (Projects 1 to 5). Not Project 4's own documents. |
| Owner | John (GitHub: jwasikye) |
| Reviewers | John approves this document before platform coding begins [Documentation Plan: How the documents get drafted] |
| Last updated | Oct 9, 2026 |
| Companion documents | [design-doc.md](design-doc.md), [adrs/](adrs/), [contracts/](contracts/), [openapi-serving-template.yaml](openapi-serving-template.yaml) |

## Source key

- **[BP x]**: Build Plans for the Five Projects, step or section x. Example: BP 0.2.
- **[BD x]**: Build Plan Decisions, the row named x.
- **[DP x]**: Documentation Plan, section x.
- **[ADR-000n]**: a platform decision record in [adrs/](adrs/).
- **[Eng n]**: engineering standard n in the build plan's Engineering standards table (sixteen rules, listed in section 2 below).
- **[OQ-nn]**: an open question in [design-doc.md](design-doc.md) section 16.

Every value here is a recorded decision or a confirmed fact. Values that are only defaults are marked **Default** and have an ADR. Anything that needs running to answer is an open question.

## 1 Introduction and goals

### 1.1 Purpose

The platform gives all five projects one shared base: a repository with tests, cloud infrastructure written as code, a nightly computer that runs the pipelines, a serving template for sites and APIs, and status and incident records. Its job is that each project can be built from its own documents without re-deciding shared parts, and that nothing surprises on cost or on data quality [BP Operating model; BP Platform skeleton].

### 1.2 Users

| User | Need | Served by |
|---|---|---|
| The owner, John | One place to build and run the five projects, with a spend that stays under $50 a month and nothing left billing after a teardown | PR-01 to PR-04, PR-20, PR-21 |
| Project builders (John, and later any engineer) | Shared parts they can rely on, with their rules written down | All requirements |
| Visitors to the sites | A page that stays up while the session box is off, and honest notices when data is late | PR-11, PR-12, PR-13 |

### 1.3 Quality goals (not ranked in the plan; listed without priority)

1. Everything is code and cheap to destroy [Eng 10].
2. Dev and live cannot damage each other [BD Dev and live].
3. Nothing surprises on cost: every paid item has a hard limit [BD Surprise costs].
4. Data is fresh every day and bad data never publishes [Eng 4, 11].
5. Public pages stay up with the session box off [Eng 16].

### 1.4 Scope boundary

In scope: the skeleton (steps 0.1 to 0.5), the operations hardening that follows (step 1B.9, after Project 1 Phase A), the engineering standards, and the rules every project inherits.

Out of scope: each project's own pipelines, data models and pages (see each project's documents); the on-call agent (second round, with its own model card); and the while-building documents listed in [README.md](README.md).

### 1.5 Constraints

- Under $50 a month, browser only [BD Budget]. The normal-month estimate is about $23 to $46 [BP Operating model; prices as of Oct 8, 2026].
- Heavy work runs on cloud servers; the owner's computer needs only a browser [BD Your computer].
- Non-commercial portfolio use [BP Assumptions].

## 2 Engineering standards (platform rules)

These sixteen rules apply to every pipeline from the first phase that touches them [BP Engineering standards]:

1. Keep raw files immutable, with source URL, fetch time and hash. Public archives that never change get a manifest of URL, size and hash instead of a full copy.
2. Carry event time and a source key on every record.
3. Make tasks idempotent and atomic: overwrite a partition, never blind-append; use the run's data interval, not now().
4. Write, audit, publish: new data lands in staging, passes checks, then goes live.
5. Give each source a data contract (schema, rules, freshness target, owner, version) and diff the schema before loading.
6. Layer dbt as staging, intermediate and marts; source() only in staging; unique and not_null tests on keys.
7. Maintain Iceberg tables as the last task of the nightly run: compact, expire snapshots, remove orphan files.
8. Keep business history in rows (SCD Type 2), not in snapshots.
9. Pick the H3 resolution from the source and join with cell_to_parent.
10. Define everything as code and make it cheap to destroy.
11. Make pipelines observable: freshness and row counts per run, a public status page, one ticket per incident.
12. Write the design down: a decision record per choice, a runbook per real incident, a design note per project.
13. Least privilege: read-only roles, scoped tools, human approval for writes, every key in Parameter Store, scanned images, source text treated as data.
14. Measure and publish the numbers: input bytes, rows, runtime, cost per run, problems caught.
15. Store every timestamp in UTC; convert only on the page.
16. Anything that runs around the clock (Lambda, Fargate) writes only to always-on storage (S3, DynamoDB, CloudWatch, X-Ray).

## 3 Functional requirements

### 3.1 Skeleton (before Project 1)

The skeleton is a walking skeleton: every main part is in place and connected end to end. It is done when the site is live with a page per project marked "coming soon", a status page is up, and a sample file flows from Spark to Iceberg to published Parquet to DuckDB in Lambda to a web page. `terraform destroy` leaves nothing billing [BP Platform skeleton].

| ID | Requirement | Step | Source |
|---|---|---|---|
| PR-01 | One public repository with the folders platform, pipelines, dbt, checks, app and docs. | 0.1 | BP 0.1 |
| PR-02 | GitHub Actions authenticates to AWS with OIDC and stores no AWS key. Any key CI needs is read from Parameter Store. | 0.1 | BP 0.1; BD Key storage |
| PR-03 | CI runs lint and tests on every push, a Terraform plan on pull requests, and an apply after approval. Gitleaks (secret scanner) and Trivy (image scanner) run in CI. | 0.1 | BP 0.1 |
| PR-04 | A Codespaces dev container opens in a browser. A spot quota of 4 vCPUs for G instances is requested in this step. | 0.1 | BP 0.1; BP Project 5 GPU access |
| PR-05 | Terraform creates the S3 buckets (raw, lake, site), the Glue catalog, a CloudFront site, the $40 budget with its action, tags, and one least-privilege IAM role per pipeline. Every key lives in Parameter Store. | 0.2 | BP 0.2 |
| PR-06 | Dev and live have separate buckets, separate Glue databases and separate roles. A dev role is refused when it writes to live data. Only merges to main reach live, after the changed pipelines pass on sample data in CI. | 0.2 | BP 0.2; BD Dev and live |
| PR-07 | Terraform state lives in its own S3 bucket, versioned, encrypted with a platform KMS key, public access blocked, readable only by the Terraform role, with S3 native locking. State never lives in the repository. | 0.2 | BP 0.2; BD Terraform state; ADR-0023 |
| PR-08 | A Terraform module starts a spot box (t4g in standard credit mode, or m7g) with k3s, and installs Airflow and Spark with their official Helm charts (Airflow in single-machine mode). | 0.3 | BP 0.3; ADR-0002, ADR-0012 |
| PR-09 | The session box has a 4-hour session limit, an idle alarm, a spot interruption handler, and a nightly schedule that starts it at 10:00 UTC and shuts it down when the pipelines finish, with a 2-hour maximum. | 0.3 | BP 0.3; ADR-0012 |
| PR-10 | Airflow's database is saved to S3 after every run and at shutdown, and restored at startup. Airflow reads connection keys from Parameter Store through its secrets backend, so the backup holds no key. | 0.3 | BP 0.3; ADR-0008 |
| PR-11 | A publish step writes gold tables as Parquet. A Lambda function runs DuckDB over them behind API Gateway with FastAPI. The sample endpoint answers with the session box off. | 0.4 | BP 0.4; ADR-0026 |
| PR-12 | A React and TypeScript site template has a map component, a lookup form, an answer card and a status page, with a preview deploy for every pull request. The page shows: "The first request after a period of inactivity may take up to 10 seconds while the service initializes." | 0.4 | BP 0.4 |
| PR-13 | Every DAG writes freshness and row counts to a metrics table. A small job publishes status.json for the status page. | 0.5 | BP 0.5; ADR-0024 |
| PR-14 | A missed freshness target or failed run sends an email. Each real incident gets a short record: what broke, the cause and the fix. | 0.5 | BP 0.5; ADR-0024 |
| PR-15 | Every Spark job has a maximum number of rows read and written and a maximum runtime. A job over either limit stops before publishing and opens an incident. | Hard limits | BP Hard limits |

### 3.2 Operations hardening (step 1B.9, after Project 1 Phase A)

Moved here from the skeleton so the first page goes live sooner [BD Extras moved later].

| ID | Requirement | Source |
|---|---|---|
| PR-20 | S3 clean-up rules on every bucket: dev data deleted after 14 days; temporary files and Spark checkpoints after 7 days; failed partial uploads after 7 days; pipeline logs after 90 days; security logs (CloudTrail, including Parameter Store reads) kept 1 year; old file versions after 30 days; raw source files and published data kept. An alarm fires if storage passes a set size. | BP 1B.9; BD Storage clean-up; ADR-0019 |
| PR-21 | Live raw files are locked against deletion or overwrite for 30 days (governance mode); dev files are not locked. | BP Raw file lock; BD Raw-file lock; ADR-0019 |
| PR-22 | Lambda cold starts are measured. Median warm latency and 95th-percentile cold-start time are reported in the README. | BP 1B.9; BD Cold starts |
| PR-23 | A weekly smoke test pulls one small sample from every source a project uses and alerts on any format change. | BP 1B.9; BD Source changes |
| PR-24 | A failed run or missed freshness target opens one GitHub issue, de-duplicated and closed on recovery. | BP 1B.9; ADR-0024 |

### 3.3 Rules every project inherits

| ID | Requirement | Source |
|---|---|---|
| PR-30 | The nightly run starts at 10:00 UTC on spot only, waits for the pipelines to finish, and has a 2-hour maximum. If no spot instance is available, the night is skipped and the next run catches up. | BD Nightly run time; BD Nightly shutdown; BP How the box is run |
| PR-31 | Iceberg maintenance is the last task of the nightly run. | Eng 7; BD Iceberg clean-up |
| PR-32 | Backfills run only during work sessions, never in the nightly run. | BD Backfills |
| PR-33 | Each project's job limits (rows, runtime, GPU hours, query limits) are set from its measured size estimate and written in its design note. | BP Hard limits table; BD Data sizes |
| PR-34 | Visitor data is stored in DynamoDB, always on, provisioned within the free tier. Point-in-time recovery is on by platform default; a project may turn it off by its own ADR. | BD Visitor data; BD DynamoDB; ADR-0006 |
| PR-35 | Personal data: email addresses are kept only in DynamoDB; elsewhere they appear as a keyed-hash code. | BD Personal data; BD Email addresses |
| PR-36 | Hiker and visitor locations are reduced to an H3 cell on the phone, so exact coordinates never reach the servers. | BD Personal data |

## 4 Quality requirements

| ID | Quality | Scenario and target | How verified | Source |
|---|---|---|---|---|
| QR-01 | Cost | The total is under $50 a month. Every paid item has a hard limit. The budget guard is $40. | Terraform shows the budget and action; each project's limits are in its design note. | BD Budget; BD Surprise costs; ADR-0013 |
| QR-02 | Teardown | After `terraform destroy`, nothing bills. | Teardown test in the skeleton gate. | BP Platform skeleton |
| QR-03 | Freshness | Every nightly run is published every day at 10:00 UTC, with a 2-hour maximum. The per-pipeline freshness target is set by each project. | Metrics table and status.json per run. | BD Data freshness; PR-13 |
| QR-04 | Availability | Public pages and the sample endpoint answer with the session box off. | Box stopped; sample endpoint called. | BP 0.4 |
| QR-05 | Security | No key in code or GitHub. Least-privilege role per pipeline. Dev cannot write live. Images are scanned. | gitleaks and Trivy in CI; role tests. | Eng 13; BD Key storage |
| QR-06 | Reliability | Every job is safe to rerun. Partitions are overwritten, not appended. A spot interruption is handled. | Rerun test in CI with sample files. | Eng 3; PR-09 |
| QR-07 | Observability | Freshness and row counts are recorded per run; one incident record per real incident; one de-duplicated GitHub issue per failure. | Status page shows the last good run; first real failure produces an email and a record. | Eng 11; PR-13, PR-14, PR-24 |
| QR-08 | Privacy | Timestamps are UTC. Personal data is kept in DynamoDB only (or hashed). Exact locations never leave the phone. | Schema review; test that no raw address or exact coordinate is stored. | BD Timestamps; BD Personal data |
| QR-09 | Data quality | Bad data never publishes, because publishing stops when a check fails. | CI test with a failing sample. | Eng 4 |
| QR-10 | Cold start | The first request after inactivity may take up to 10 seconds, and the page says so. | Notice on the page; measured times in the README. | BP 0.4, 1B.9 |

## 5 Acceptance criteria (the build plan's "Done when" checks)

| Step | Done when | Verification |
|---|---|---|
| 0.1 | CI is green on the empty skeleton, and the dev container opens in a browser. | CI run; Codespaces open. |
| 0.2 | `terraform apply` and `destroy` both work; the state bucket is the only place state exists; the budget and action are in place; a dev role is refused when writing live data. | Apply and destroy; state location check; budget resource; role test. |
| 0.3 | One command brings the box up; a sample Spark job writes an Iceberg table registered in Glue; the nightly schedule runs the sample DAG and shuts the box down; Airflow's run history survives a teardown; dev and prod are separate. | Sample run; teardown and restore test. |
| 0.4 | The site is live with project placeholders; the sample endpoint answers with the box off. | Site URL; box stopped; endpoint call. |
| 0.5 | The status page shows each pipeline's last good run; the first real failure sends an email and gets an incident record. | Status page; a real failure (not a staged one). |
| 1B.9 | The clean-up rules show on every bucket; warm and cold-start latency are in the README; the weekly smoke test runs; the next real failure opens one issue. | Bucket configuration; README; schedule; issue. |

First-run checks (skeleton, from BP Platform skeleton): the GPU quota request is approved (needed by Project 5); each image (Airflow, Spark, Kafka, Superset, PostgreSQL) runs on the ARM box; Airflow's database restores from S3 on a fresh box; memory use on the 32 GB box is measured with the real stack; the session limit and idle shutdown trigger in normal use. Each check has a fallback if it fails; the plan records none, so they are open questions in [design-doc.md](design-doc.md) section 16.

## 6 Traceability

| Build step | Requirements | Quality |
|---|---|---|
| 0.1 | PR-01 to PR-04 | QR-05 |
| 0.2 | PR-05 to PR-07 | QR-01, QR-02, QR-05 |
| 0.3 | PR-08 to PR-10, PR-30 to PR-32 | QR-06 |
| 0.4 | PR-11, PR-12 | QR-04, QR-10 |
| 0.5 | PR-13, PR-14 | QR-07 |
| 1B.9 | PR-20 to PR-24 | QR-03, QR-07 |
| Rules | PR-33 to PR-36 | QR-01, QR-08, QR-09 |

## 7 Decisions still needed from John

These are choices John has to make. None is needed to write the other platform documents.

| ID | What | Blocks |
|---|---|---|
| OQ-P01 | Approved by John, Oct 9, 2026: the defaults in ADR-0024 (SNS email, metrics table in the lake) and ADR-0032 (SHA-256). | PR-13, PR-14, PR-24 |
| OQ-P02 | Partly approved by John, Oct 9, 2026: the 4-hour session limit and the 2-hour nightly maximum. The idle-alarm duration is still to be measured. | PR-09 |

## 8 Open questions that need a spike

Listed in [design-doc.md](design-doc.md) section 16 (OQ-P03 to OQ-P10).
