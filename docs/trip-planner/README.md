# Will I have signal out there?

A trip planner for hikers, campers and backpackers. Pick a trail and see where each phone carrier has coverage, where it drops out, when a Starlink Direct-to-Cell satellite text could get through, and how much to trust the coverage map at each point.

This folder is the documentation for Project 1. It is written so that someone who has never seen the project can build it from these documents alone.

| Field | Value |
|---|---|
| Status | Documents complete for review. Draft pending John's approval. **No code exists yet** |
| Owner | John |
| Last updated | Oct 9, 2026 |
| Live link | None yet. Phase A (live) has not started |

---

## 1. The project in plain words

- **Who it is for:** hikers, campers and backpackers who want to know whether their phone will work on a trail, and whether a satellite text could reach someone.
- **What it shows:** for each point along a trail, whether the carrier's coverage map says there is signal, and whether a satellite overhead could reach the phone, with canyon walls and mountains taken into account.
- **How far to trust it:** the coverage map is a model's claim. Where measured speed tests exist nearby, the page gives a confidence level. Where they do not, the page says "Not enough measurements here; the coverage map's claim is unverified." It does not guess.
- **Late data is never hidden.** If the nightly update fails, the page keeps the old data and shows a visible late notice with the time of the last good run.
- **Hikers can report.** In Phase B, a hiker with no signal can tap "I had signal here" or "I had no signal here". The phone reduces its location to a cell about 350 m across, and exact coordinates never leave the phone.
- **Phase A (first live version):** Grand Canyon's Bright Angel, South Kaibab and North Kaibab trails, with T-Mobile, for the next 24 hours of satellite passes. Phase B adds every carrier, measured speeds, a warehouse, the confidence model, a trip assistant and hiker reports. Phase C (second round) adds every national park, route upload and an offline trip pack.

## 2. How it works, in one picture

```
Public sources ──> nightly pipelines on a rented server (10:00 UTC, about 45 minutes, 2-hour maximum)
(CelesTrak, FCC,      │  orbit ingest, trail points, terrain horizon, satellite windows,
 NPS, Copernicus,     │  coverage flags, dbt models, publish gate
 Ookla, OpenCelliD)   ▼
                    published tables (Parquet on S3) ──> serving API (Lambda, DuckDB) ──> trail page
                                                                                        │
Phase B: hiker's phone ──> report API (Lambda) ──> DynamoDB ──> nightly copy ──> lake ──┘
                                                                  └──> Snowflake marts
```

The page never waits for the nightly run. It reads the last published tables, so it answers while the rented server is switched off.

## 3. Documents in this folder

| Document | What it is for | When it was written |
|---|---|---|
| [README.md](README.md) | This page: what the project is, the document map and the reading order | Before coding |
| [requirements.md](requirements.md) | Who the project is for; features by phase; functional and quality requirements; acceptance criteria | Before coding |
| [design-doc.md](design-doc.md) | The design in 17 sections: context, architecture (C4 diagrams), every component with its functions, runtime flows, data model, API, deployment, cross-cutting concerns, testing, alternatives, risks, open questions and glossary | Before coding |
| [adrs/](adrs/) | Architecture decision records: one short record per significant decision, with alternatives and consequences. The superseded record 0006a was removed on Oct 9, 2026 as a duplicate old version; 0006 is the amended record | Before coding |
| [contracts/](contracts/) | Data contracts (ODCS v3, YAML) for every source and every published table: schema, rules, freshness, owner, version and storage location | Before coding |
| [openapi.yaml](openapi.yaml) | The API specification (OpenAPI 3): every endpoint, request, response, error and limit | Before coding |
| [../Platform/platform-requirements.md](../platform/platform-requirements.md) | The shared platform parts Project 1 depends on: repository and CI, cloud base, the session box, the serving template, status and incidents, engineering standards, tools and keys | Before coding |
| [operations.md](operations.md) | Schedules, freshness targets, monitoring, cost limits, runbooks for each known failure, incidents and backups | Kept current while building |
| [security-and-privacy.md](security-and-privacy.md) | Threat model, personal-data inventory with retention, access matrix, licence and attribution register, and open privacy questions | Kept current while building |
| [model-card.md](model-card.md) | For the two AI components: intended use, out-of-scope use, data, evaluation plan, known failure cases and updates | Kept current while building |
| [changelog.md](changelog.md) | What changed in the documents and, later, in each phase | Kept current while building |
| Reference from code | Function reference from docstrings, the dbt docs site and the API docs page | **Not written yet.** Generated from the code once the code exists |

## 4. Reading order

1. **This page**, then [requirements.md](requirements.md) sections 1 to 3 for scope.
2. [design-doc.md](design-doc.md) sections 2, 3 and 6: the summary, the constraints, and the diagrams.
3. [design-doc.md](design-doc.md) section 7: every component, with its functions and the four hardest parts in full.
4. [design-doc.md](design-doc.md) sections 8 and 9: the runtime flows and the data model. Then the contracts.
5. [openapi.yaml](openapi.yaml) and [design-doc.md](design-doc.md) section 10: the API.
6. [../Platform/platform-requirements.md](../platform/platform-requirements.md): the platform parts, before the first pipeline.
7. [adrs/](adrs/): read the decision behind any value that looks odd.
8. [operations.md](operations.md), [security-and-privacy.md](security-and-privacy.md) and [model-card.md](model-card.md) before anything goes live.
9. [design-doc.md](design-doc.md) section 16: the open questions. Check each one that touches the part you are building.

## 5. Build order, by dependency

This is the order the parts depend on each other. It has no dates. The documents say what to build and in what order it must happen. They do not say when.

**Before Project 1 (platform, from [../Platform/platform-requirements.md](../platform/platform-requirements.md))**
1. Repository, CI, dev container (section 2).
2. Cloud base in Terraform: buckets, Glue, CloudFront, budget, roles, Parameter Store, state (section 3).
3. Session box with k3s, Airflow and Spark, the nightly schedule, and the Airflow database backup (section 4).
4. Serving template: Parquet publish, Lambda with DuckDB behind API Gateway, the site template (section 5).
5. Status page, metrics table and alerts (section 6).

**Phase A, in order**
1. C8 contract diff, and C1 orbit ingest with C2 selector (the [DTC] tag and the cross-check). Needs the first-run check on a real CelesTrak file (OQ-6, OQ-20).
2. C3 trail loader and C4 terrain horizon. Needs the NPS and Copernicus first-run checks (OQ-8, OQ-36).
3. C5 satellite windows. Needs C2 and C4, and the measured size (OQ-1).
4. C6 FCC coverage. Needs the FCC file size (OQ-7).
5. C7 dbt models on DuckDB, then C9 publish gate, then C10 publisher. The gate stops a publish when a check fails.
6. C11 serving API and C12 trail page. Gate: the page answers for every main trail with the session box off (AC-1A.6).

**Phase B, after Phase A is live**
1. C13 all carriers, Ookla and OpenCelliD. Needs the Ookla first-run check (OQ-10).
2. C14 orbit update stream (Kafka, availableNow), which needs C1.
3. C15 Snowflake warehouse and C16 lineage (Marquez, dbt docs). Needs the Snowflake and ARM Marquez first-run checks (OQ-4, OQ-5).
4. C21 report button on the phone, C22 report API with limits, C23 nightly copy and set-aside. These need the limits and N decisions (OQ-12, OQ-26).
5. C17 confidence model. Needs the labels from C23, Databricks access (OQ-3) and the model family (OQ-18).
6. C18 AI foundations (call log, traces, MCP tools), then C19 assistant, then C20 evals in CI. The eval thresholds are set by John (OQ-16).
7. C24 operations hardening: clean-up rules, cold-start measurement, weekly smoke test, incident issues.

**Second round:** Phase C features (national scope, route upload, offline trip pack, model comparison). Their acceptance checks are written when Phase C is designed.

## 6. Accounts and keys needed

| Account or key | Needed for | Phase | Status |
|---|---|---|---|
| AWS account, in us-east-1 for dev and live | Everything | Platform | Region chosen by John (OQ-42, ADR 0034) |
| GitHub, with a public repository | Code, CI and the public site | Platform | Needed from the first commit |
| Databricks Free Edition | Training the confidence model | B | Upload is untested (OQ-3) |
| Snowflake trial | Warehouse and metrics | B | Connection untested (OQ-4) |
| Model API account, with a $10 monthly spend limit set before the first call | Assistant and LLM judge | B | Anthropic API, cheapest Claude model (ADR 0034) |
| Public data sources (CelesTrak, NPS, FCC, Copernicus, Ookla, OpenCelliD, U.S. Census TIGER/Line) | Inputs | A and B | No key is recorded. Confirm in the first-run checks |

Every key is stored in AWS Parameter Store and read at run time. None is written in code or in GitHub. See [../Platform/platform-requirements.md](../platform/platform-requirements.md), section 9.

## 7. Conventions

- **Times** are stored in UTC and converted to local time only on the page.
- **Identifiers:** FR is a functional requirement, QR a quality requirement, AC an acceptance criterion, ADR an architecture decision record, OQ an open question, C a component of the design doc. All are defined in [requirements.md](requirements.md) and [design-doc.md](design-doc.md).
- **Values** are either recorded decisions (cited by ADR or by "Decided by John") or confirmed facts. Anything else is an open question in [design-doc.md](design-doc.md), section 16, with a matching GitHub issue. The issues are not yet created.
- **Names** of tables, functions, endpoints and buckets are proposals until John approves them (OQ-21).
- **Environments:** `dev` and `live` are fully separate. A dev role cannot write live data.
- **Licences:** the Ookla notice is shown exactly as written in ADR 0013. Every source is credited.

## 8. What this set does not contain

- **A schedule.** The documents say what to build, in what order and against what checks. The schedule is kept apart from them.
- **The platform's own document set.** The platform's documents are not written yet. [../Platform/platform-requirements.md](../platform/platform-requirements.md) holds the parts Project 1 needs.
- **The reference generated from code.** It does not exist until the code does.
- **Setup commands.** These are written with the code, in the repository's own README, once there is code to run.
- **GitHub issues for the open questions.** These are to be created. They are not created yet.

## 9. Approval

John approves each document before coding of that part begins. Coding of Project 1 does not start until the requirements, design doc, ADRs, contracts and API specification are approved.
