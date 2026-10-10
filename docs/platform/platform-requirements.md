# Platform requirements for Project 1

| Field | Value |
|---|---|
| Status | Draft for review. Coding of the platform parts does not begin until John approves this document |
| Owner | John |
| Reviewers | John |
| Last updated | Oct 9, 2026 |
| Scope | The parts of the shared platform that Project 1 depends on, specified in full |
| Related | [design-doc.md](design-doc.md) (section 11, deployment), [requirements.md](requirements.md), [operations.md](operations.md), [security-and-privacy.md](security-and-privacy.md) |

The platform is the shared system that all five projects run on. Its own document set (design doc, ADRs and shared contracts) is not written yet. This file holds every platform part that Project 1 needs, so that Project 1 can be built from the documents alone. This file sits in the platform folder with the other platform documents (see the README there).

Values marked "proposed" are names or layouts that John approves with this document (OQ-21). Values marked "estimate" come from public price pages as of Oct 8, 2026 and are rechecked before use.

> **Status note.** This file is the working draft written during the Project 1 review. The platform document set in this folder (design doc, requirements, ADRs, contracts, API, operations, security) is the set of record. Where the two differ, the set of record wins.

---

## 1. What the platform is and how it is built

- **Walking skeleton.** The platform starts as a small version of the whole system, with every main part running on Kubernetes and connected end to end. It then grows while it keeps running. The skeleton is done when a sample file flows from Spark to Iceberg to a published Parquet file to DuckDB in Lambda to a web page, and `terraform destroy` leaves nothing billing.
- **Two environments.** `dev` is a copy for trying things. `live` is the public site. Both come from the same code and the same container images. They never share a bucket, a Glue database, a DynamoDB table or an IAM role.
- **Small changes, merged often.** Work happens on short-lived branches merged to `main` quickly. CI runs on every change.
- **Tested before deployed.** On every merge to `main`, CI runs the changed pipelines with Spark on small sample files on GitHub's hosted machines. The AWS session box stays off for this. Only when those tests pass does a change deploy to `dev`, and then to `live`.
- **Preview links.** Every website change gets a preview link before it goes live.
- **No real failures are staged.** Tests use small sample files. Real incidents are recorded when they happen (section 6).

## 2. Repository and CI (platform step 0.1)

- One public repository with the folders `platform`, `pipelines`, `dbt`, `checks`, `app` and `docs`. The repository is public because the cost model depends on GitHub Actions being free for public repositories.
- GitHub Actions runs lint and tests on every push, a Terraform plan on every pull request, a Terraform apply after approval, and gitleaks and Trivy scans.
- GitHub Actions reaches AWS through OIDC (OpenID Connect). The repository stores no AWS keys. Any key CI needs is read from Parameter Store (section 3).
- A dev container opens in GitHub Codespaces so that all editing happens in a browser. AWS is controlled from AWS CloudShell.
- The spot quota request for G instances is made at this step, because the project that uses GPUs (Project 5) needs it. Project 1 does not use GPUs.

## 3. Cloud base (platform step 0.2)

All resources are written in Terraform. Every resource can be destroyed with `terraform destroy`.

| Resource | Requirement |
|---|---|
| S3 buckets | Raw (`{env}-signal-raw`), lake (`{env}-signal-lake`, which also holds the `published/` prefix) and the public site. Names are proposed (design doc, section 9.1) |
| Glue Data Catalog | One database per environment, `{env}_signal`, holding the Iceberg tables |
| CloudFront | Serves the static trail page from the site bucket |
| AWS Budget | $40 a month with an action that denies new launches and stops the box. It is a backup; the session limit and idle alarm are the main guards |
| IAM | One least-privilege role per pipeline. The dev roles cannot write live data. A refusal test proves this |
| Parameter Store | Every key and password is stored here as an encrypted SecureString. None is stored in code, in GitHub or on the box |
| Terraform state | A dedicated S3 bucket that is versioned, encrypted with a customer-managed KMS key, has public access blocked, and is readable only by the Terraform role. It uses Terraform's built-in S3 locking. The state file never lives in the repository |
| Region | us-east-1 (N. Virginia), chosen by John (OQ-42, ADR 0034) |

## 4. Session box (platform step 0.3)

The session box is the rented AWS server that runs Airflow, Spark and the other batch tools. It exists only during a run or a work session.

| Item | Requirement |
|---|---|
| Instance | Spot. `t4g.2xlarge` (8 vCPU, 32 GB) for everyday work in CPU credit mode `standard`, or `m7g.2xlarge` (not burstable) for heavy batch. Both have 32 GB, which is the memory limit to check (open question below) |
| Images | arm64. Each image's manifest is checked before first use |
| Orchestration | k3s (a lightweight Kubernetes). Each pipeline has its own memory and CPU limits, and failed services restart automatically |
| Installed with official Helm charts | Airflow in its single-machine mode; Spark with its operator; Kafka (one broker, Phase B); PostgreSQL for Airflow's own bookkeeping only; Superset and Grafana (Phase B, during sessions only) |
| Session limit | The box stops 4 hours after it starts |
| Idle shutdown | A CloudWatch alarm stops the box when it is idle |
| Spot interruption | A handler reacts to the two-minute spot warning. Every job is safe to rerun |
| Nightly start | 10:00 UTC (3 a.m. Arizona, 6 a.m. US Eastern) |
| Nightly stop | When every pipeline finishes. Hard maximum 2 hours. Hitting the maximum is recorded as an incident |
| Spot only for the nightly run | If spot capacity is unavailable, that night is skipped and the next run catches up |
| Backfills | Long historical backfills run only during work sessions, never in the nightly run |
| Airflow's database | Saved to S3 after every run and at shutdown, and restored at startup. If the latest copy is lost, the pipelines are safe to rerun |
| Airflow's keys | Read from Parameter Store through Airflow's built-in secrets backend, so the saved database never contains a key |
| Dev and live | The same code. Separate buckets, databases and roles |
| Network | No NAT gateway. No idle Elastic IP. Public IPv4 only while the box runs |
| Start and destroy | Started per session from Terraform and destroyed afterwards |

Open platform questions for this section:

- Does the full stack fit in 32 GB of memory? It is answered by running the stack on the session box (design doc, section 16).
- Does the ARM build of the pinned Marquez version succeed (OQ-5)? If not, the lineage tool choice is revisited.
- How dbt on DuckDB reads Iceberg tables (OQ-40).

## 5. Serving template (platform step 0.4)

The serving template is the setup every project's website and API reuse.

- **Publish step.** The publisher (design doc, component C10) writes gold tables as Parquet to the `published/` prefix of the lake bucket. The publisher replaces a table in one step, so readers never see part of a publish.
- **Serving API.** A Lambda function runs DuckDB over the published Parquet, behind API Gateway, with FastAPI. It reads the published data only.
- **Which API Gateway type.** The HTTP type serves public pages. The REST type is used only where API keys and per-key usage plans are needed. Project 1 issues no API keys, so it uses the HTTP type.
- **Always-on writes.** A Lambda function, or any other service that runs at any hour, writes only to always-on storage: S3, DynamoDB, CloudWatch and X-Ray. The session box is not always on, so Lambda never depends on it (engineering standard 16).
- **Website.** A React and TypeScript site with a map component, a lookup form, an answer card and a status page. Each page gets a preview link per pull request.
- **Cold-start notice.** The site shows exactly this text: "The first request after a period of inactivity may take up to 10 seconds while the service initializes."
- **Acceptance.** The sample endpoint answers with the session box off.

## 6. Status and incidents (platform step 0.5)

- Every pipeline writes freshness and row counts to a metrics table after each run. The metrics table is proposed as an Iceberg table, `pipeline_metrics`, in the lake (OQ-21).
- A small job writes `status.json` after each run. The status page reads it and shows each pipeline's last good run.
- A missed freshness target or a failed run sends an email. Email is proposed through Amazon SNS (OQ-21).
- Each real incident gets a short record: what broke, the cause and the fix. The format is in [operations.md](operations.md), section 5.
- From Phase B (step 1B.9), each failure also opens one GitHub issue. Duplicate failures are merged into one issue, and the issue closes when the pipeline recovers.

## 7. Engineering standards

These sixteen rules apply to every pipeline from the first phase that touches it. The design doc cites them by number.

| # | Rule | Why |
|---|---|---|
| 1 | Keep raw files unchanged, with source URL, fetch time and hash. For public archives that never change (NPS, Copernicus elevation, Ookla, OpenCelliD), keep a manifest of URL, size and hash instead of a copy | Any result can be replayed and audited at low storage cost |
| 2 | Carry event time and a source key on every record | Duplicates and replays become harmless |
| 3 | Make tasks idempotent and atomic: overwrite a partition, never blind-append, and use the run's data interval instead of the current time. Keep history by adding one partition per pull | Retries and backfills stay safe |
| 4 | Write, audit, publish: new data lands in staging, passes checks, then goes live | Bad data never reaches the site |
| 5 | Give each source a contract with schema, rules, freshness target, owner and version, and diff the schema before loading | An upstream change fails loudly and early |
| 6 | Layer dbt as staging, intermediate and marts. Use `source()` only in staging, and put unique and not_null tests on keys | Lineage is easy to review |
| 7 | Maintain Iceberg tables on a schedule: compact, expire snapshots and remove orphan files, as the last task of the nightly run | Small files and metadata grow with every commit |
| 8 | Keep business history in rows (SCD Type 2, one partition per pull), not in snapshots | Snapshot expiry deletes old versions |
| 9 | Pick the H3 resolution from the source (the cell just larger than the pixel) and join across sources with `cell_to_parent`: resolution 9 for FCC files and hiker reports, 8 for elevation rasters and Ookla tiles, 4 for 0.25 degree weather grids | Avoids false precision and mismatched joins |
| 10 | Define everything as code and make it cheap to destroy | No stored keys and no surprise bills |
| 11 | Make pipelines observable: freshness and row counts per run, a public status page, and one ticket per incident | Problems surface before users see them |
| 12 | Write the design down: a decision record per choice (including when not to use a tool), a runbook per real incident, and a design note per project with volumes, failure modes and what changes at 100 times the scale | Design reviews work from written records |
| 13 | Least privilege: read-only roles and allowlists for agents, scoped tools, write actions only through human approval, every key in Parameter Store and none in code or GitHub, scanned images, and source text treated as data, never as instructions | Agents that touch real systems are the main safety risk |
| 14 | Measure and publish the numbers: input bytes, rows, runtime, cost per run, problems caught, eval scores and users | Claims stay honest and checkable |
| 15 | Store every timestamp in UTC. Convert to local time only on the page | Sources mix UTC, local and unknown time zones, and hikers read local time |
| 16 | Anything that runs around the clock writes only to always-on storage (S3, DynamoDB, CloudWatch, X-Ray). The session box picks the data up in the nightly run | Kafka, Grafana and Superset exist only while the box is on |

## 8. Tools and the alternatives that were rejected

Each job has one tool. Where two tools did the same job, one was removed, and the reason is recorded.

| Job | Tool | Alternatives removed | Why this one |
|---|---|---|---|
| Batch and streaming processing | Spark (PySpark and Structured Streaming) | Flink | One engine for batch and streaming, and it handles the largest jobs |
| Event transport | Kafka, one broker | None | Decouples live sources from processing and allows replay |
| Orchestration | Airflow | None | Schedules, retries and backfills |
| Lake tables and catalog | Iceberg on S3, AWS Glue catalog | None | Every engine reads the same tables without copies |
| Transformations | dbt: DuckDB for development and CI, Snowflake for production marts | dbt targets on Trino, BigQuery and Databricks | The same models run in both places |
| Serving queries | DuckDB in Lambda and on the box | Trino | No server, nothing billed when idle, fast at the sizes served |
| Warehouse, dashboards, metrics | Snowflake reading Iceberg through Glue, dbt marts, MetricFlow metrics | BigQuery | One warehouse for marts, dashboards and metric definitions |
| ML training and experiment tracking | Databricks Free Edition with MLflow | Self-hosted MLflow | Free managed MLflow and model registry |
| Visitor data (reports, votes, counters) | DynamoDB | PostgreSQL on the box | Always on and writable while the box is off; free tier covers this traffic |
| Lineage | OpenLineage with Marquez, and the dbt docs site | DataHub | Lineage from Airflow and Spark, plus table documentation |
| Infrastructure | Terraform | OpenTofu | The name most employers recognize; the same locked-down state practice applies |
| Kubernetes | k3s | Docker Compose | Hands-on Kubernetes experience. It also gives each pipeline its own memory and CPU limits and restarts failed services, and it carries over unchanged to a multi-server test |
| Data quality | Great Expectations at the publish gate; dbt tests on models | None | Different stages: raw data before publish, models after build |
| Dashboards | Superset for business data on Snowflake; Grafana for platform health. Both work during sessions only. Snapshot charts are published to the site each night | None | Two jobs: business data and system health |

Tool use by Project 1:

| Tool | First used | Phase |
|---|---|---|
| Airflow, Spark, Iceberg with Glue, DuckDB in Lambda, React, Terraform, CI, dev-first deploys, preview links, Parameter Store, dev and live separation, nightly run | Platform skeleton | Skeleton |
| dbt (DuckDB target), Great Expectations, data contracts, H3 utilities, terrain processing | Project 1 | A |
| Kafka and Structured Streaming (availableNow) | Project 1 | B |
| Snowflake, dbt Snowflake target, MetricFlow, Superset | Project 1 | B |
| Databricks and MLflow | Project 1 | B |
| OpenLineage with Marquez, dbt docs catalog | Project 1 | B |
| Model calls logged to S3, X-Ray tracing, MCP server, eval harness | Project 1 | B |
| DynamoDB visitor data, with nightly copy to the lake and Snowflake | Project 1 | B |

### Marquez build

Marquez and its web page publish only x86 images. The platform builds ARM images of one pinned Marquez version once, in GitHub Actions. It rebuilds only when John chooses to upgrade. The build is a first-run check in Phase B. If it fails, the lineage tool choice is revisited (OQ-5).

### Databricks Free Edition limits

Serverless only. A daily fair-use quota. Limited outbound internet. Non-commercial. These limits are why results are exported by hand (ADR 0014).

### Snowflake settings

A 30-day trial with $400 of credits starts in Phase B (step 1B.3). After the trial, the warehouse is X-Small with a 60-second auto-suspend and a resource monitor that suspends it at 3 credits a month. Every query has a time limit (FR-32). The cost is about $6 a month at $2 a credit on Standard edition (estimate; check edition and region).

## 9. Keys and secrets

Every key is stored in Parameter Store and read at run time. No key is written in code, in GitHub or in the Airflow database.

| Secret | Used by | Phase |
|---|---|---|
| Model API key | Trip assistant, its evals and the LLM judge | B |
| Snowflake credentials | Warehouse refresh and dbt marts | B |
| Databricks credentials | Upload of training data and MLflow access | B |
| Airflow connection keys | Airflow connections to AWS and other services | A |

No key is recorded for the public sources (CelesTrak, NPS, FCC, Copernicus and Ookla open data, OpenCelliD). Confirm that in the first-run checks. The GitHub OIDC role is not a secret; it is named in the Terraform configuration.

## 10. Phase C and the second round

Platform parts that arrive in the second round are not needed by Project 1: the on-call agent (its design is written in the second round) and a one-day EKS deploy to compare with k3s. Project 1 Phase C is also in the second round and has no acceptance checks yet (design doc, section 4.2).
