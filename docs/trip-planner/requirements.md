# Project 1: Will I have signal out there? Requirements

| Field | Value |
|---|---|
| Status | Approved by John (Oct 28, 2026) |
| Owner | John |
| Reviewers | John (approves before coding of this project begins) |
| Last updated | Oct 28, 2026 |
| Sources | Build Plans for the Five Projects (Oct 8, 2026), Build Plan Decisions (Oct 9, 2026), Documentation Plan (Oct 9, 2026) |
| Related | [design-doc.md](design-doc.md), [adrs/](adrs/), [contracts/](contracts/), [openapi.yaml](openapi.yaml), [../Platform/platform-requirements.md](../platform/platform-requirements.md), [operations.md](operations.md), [security-and-privacy.md](security-and-privacy.md), [model-card.md](model-card.md), [README.md](README.md), [changelog.md](changelog.md) |

Conventions used in this document:

- A value is either a recorded decision (cited as an ADR, an architecture decision record in [adrs/](adrs/)) or a confirmed fact from the three source files. Anything else is an open question, listed as OQ-n (open question n) in section 16 of the design doc.
- Terms are defined in the glossary in section 17 of design-doc.md. Phase A, B and C and the platform skeleton are defined in section 1 of design-doc.md. "Satellite window" is a period when a satellite is reachable; "prediction span" is the 26 hours the pipeline predicts; "log retention period" is how long logs may be kept with internet addresses. "Valid until" in prose is `valid_until` in code.
- The rules cited by number are listed with their content in section 1 of design-doc.md. In short: engineering standard 1 keep raw files unchanged; 2 event time and source key on every record; 3 idempotent and atomic tasks; 4 write, audit, publish; 5 contracts and schema diff; 6 dbt layers; 13 least privilege; 15 UTC timestamps; platform step 0.2 cloud base with separate dev and live; platform step 0.5 status page and incident records. "Engineering standard N" means rule N in the build plan's "Engineering standards" table. "The page" means the public trail page.
- Each functional requirement names who acts (a component from design-doc.md section 7, or a person) and is checked by the acceptance criterion of its feature (section 6) or by the quality scenario that names it (section 5).
- "Done when" checks from the build plan are reproduced as the acceptance criteria (AC) of each feature, without change.
- Requirement identifiers: F = feature, FR = functional requirement, QR = quality requirement, AC = acceptance criterion.
- Names of tables, endpoints and fields that appear below are proposals of the design documents unless a source file names them. They are approved with the documents (OQ-21).

---

## 1. Introduction and goals (arc42 section 1)

### 1.1 What the project is

A trip planner for hikers, campers and backpackers. The visitor picks a trail or campsite and sees:

- where each carrier has coverage and where it drops out;
- when a Starlink Direct-to-Cell satellite text could get through, accounting for canyon walls and mountains that block the sky;
- how much to trust the coverage map at each point.

Direct-to-Cell texting also needs T-Mobile service (in the United States) and a supported phone, and the page says so. T-Mobile is the Phase A carrier.

Story, as decided by John: the project is about people going out in nature and whether they will have a connection (Build Plan Decisions, "Projects and scope").

### 1.2 Quality goals

The top quality goals, in priority order for this project. Each is expanded as a quality requirement in section 5.

| Priority | Goal | Why it matters here | Basis |
|---|---|---|---|
| 1 | Never present late or unverified information as current or certain | A hiker may act on a satellite window or a coverage claim | ADR 0006, ADR 0008 |
| 2 | Hikers' locations stay private | Exact coordinates never leave the phone; no internet addresses used | ADR 0009, ADR 0011 |
| 3 | The public page answers while the session box (the rented AWS server that runs the pipelines) is off | The box runs only about 45 minutes a night | Build plan 1A.6, platform skeleton (the first build stage of the platform) |
| 4 | Cost never surprises | Budget under $50 a month, a hard limit on every paid item | Decisions, "Cost, limits and operations" |

### 1.3 Stakeholders

| Stakeholder | Expectation |
|---|---|
| Hikers, campers, backpackers (public visitors) | Accurate, honest signal and satellite information for the trail they pick; ability to report signal from the trail |
| John (owner and operator) | A live page that does not break while building; costs under limits; documents to build from |
| Data providers (CelesTrak, FCC, NPS, Copernicus, Ookla) | Credit and license terms respected (section 5, QR-12) |

---

## 2. Users and needs

| User | Situation | Needs | Features that serve it |
|---|---|---|---|
| Hiker planning a trip at home | Choosing a trail and wanting to know where to check in with family | See coverage by carrier along the trail; see when a satellite text could get through; see how far to trust the map | F-1A.4, F-1A.6, F-1B.1, F-1B.4, F-1B.6 |
| Hiker on the trail with no signal | Has just found that a place has or lacks signal | Report "I had signal here" or "I had no signal here" without signal at that moment, without giving away exact position | F-1B.8 |
| Camper or backpacker packing for a trip | Will lose signal before reaching camp | Save the map, satellite windows and check-in plan to the phone before losing signal | F-1C.2 (second round) |
| Hiker using a trail app | Has a route as a GPX file | Upload a route and get the same information | F-1C.1 (second round) |
| Owner and operator (John) | Runs the nightly pipeline and the site | Know when a run fails; know cost; rerun safely; see data quality | F-1A.5, F-1B.3, F-1B.5, F-1B.9 |

Needs that apply to every visitor:

- The page shows the time until which the predictions are valid, in the hiker's local time, and a late notice when the predictions are late.
- The page states what Direct-to-Cell texting requires (T-Mobile service, supported phone).
- The page says so when the data cannot answer.

---

## 3. Features by phase

Phases follow the build plan: A is live and small, B adds depth, C is the second-round scale phase. Feature identifiers equal the build plan step numbers.

### 3.1 Phase A: live

Scope (ADR 0001, ADR 0020): Grand Canyon National Park's Bright Angel, South Kaibab and North Kaibab trails, one carrier (T-Mobile), the next 24 hours of satellite passes (26 hours are predicted so there is no daily gap, ADR 0019). Decided by John, Oct 9, 2026.

| Feature | Name | Summary |
|---|---|---|
| F-1A.1 | Orbit ingest | Airflow DAG pulls CelesTrak GP data as JSON and selects Direct-to-Cell satellites by the [DTC] name tag, cross-checked against altitude and inclination |
| F-1A.2 | Trails and terrain | NPS trail lines for Grand Canyon sampled every 50 meters; terrain horizon per point from Copernicus 30-meter elevation, stored in Iceberg |
| F-1A.3 | Satellite windows | SGP4 propagation at 1-minute steps for 26 hours (the page says the next 24 hours); satellite windows per trail point when a satellite is above 10 degrees and above the terrain horizon; each run stamped with a valid until time |
| F-1A.4 | Cell coverage | FCC mobile coverage (H3 resolution 9 files) for one carrier in Arizona; each trail point marked covered or not |
| F-1A.5 | Models and checks | dbt on DuckDB (staging, intermediate, small star schema); contracts for CelesTrak, FCC, NPS trails and elevation; Great Expectations publish gate |
| F-1A.6 | Trail page | Gold tables published; React page with a strip map (bars where the carrier has coverage, no bars where it does not) and the next satellite windows along the trail; "Predictions valid until [time]"; late data shown with a visible late notice and the time of the last good run |

### 3.2 Phase B: depth

| Feature | Name | Summary |
|---|---|---|
| F-1B.1 | Every carrier and measured speeds | FCC coverage for every carrier for the park; Ookla open mobile speed-test data for Arizona; license notice |
| F-1B.2 | Orbit update stream | New element sets published to Kafka; Structured Streaming job with availableNow trigger finds changed satellites and triggers re-propagation |
| F-1B.3 | Warehouse, metrics and lineage | Snowflake over Glue, dbt marts with SCD Type 2 carrier coverage, MetricFlow metrics, Superset dashboard, resource monitor, OpenLineage with Marquez, dbt docs |
| F-1B.4 | Coverage confidence model | Model of how likely the FCC map is right; confidence only where enough speed tests exist; trained in Databricks, tracked in MLflow, exported to the repo by hand |
| F-1B.5 | AI foundations | Call log, tracing to AWS X-Ray, MCP server (tool interface for AI models) for metrics, read-only logged SQL fallback, versioned prompts, structured output, eval harness, daily cap, $10 spend limit |
| F-1B.6 | Trip-planning assistant | Plain-language question returns a cited check-in plan |
| F-1B.7 | Evals in CI | 30 or more graded questions, calibrated LLM judge, red-team set of 20 or more prompts, votes in DynamoDB, A/B test of two prompt versions |
| F-1B.8 | Hiker signal reports | "I had signal here" and "I had no signal here" buttons; H3 cell computed on the phone; offline queue; rate limits; DynamoDB; labels for the model |
| F-1B.9 | Operations hardening | S3 clean-up rules, cold-start measurement, weekly source smoke test, de-duplicated GitHub issues for failures |

### 3.3 Phase C: scale (second round)

Starts only after every project has reached Phase B.

| Feature | Name | Summary |
|---|---|---|
| F-1C.1 | National scope and route upload | Every national park; a route upload (a GPX file from any trail app) |
| F-1C.2 | Offline trip pack | Save the map, satellite windows and check-in plan to the phone before losing signal |
| F-1C.3 | Model comparison | Compare the cheapest model with a stronger one in the eval suite; switch only if the scores justify the cost |

Phase C features have no "Done when" checks in the build plan. Their requirements and acceptance criteria will be written when the second round is planned; this is a recorded gap (Decided by John, Oct 9, 2026: write them when Phase C is designed), not guessed here.

---

## 4. Functional requirements

Each requirement is traceable to a build plan step (the Feature column) and to a decision where one exists.

### 4.1 Phase A

Numbering note: IDs are never renumbered. Some IDs appear out of order because requirements were added or split later: FR-63 to FR-65 (Phase C) are listed after Phase B; FR-66 to FR-69 follow FR-62; FR-70 to FR-74 follow FR-54 and replace what FR-54 used to say about limits; FR-75 and FR-76 follow FR-6.

| ID | Requirement | Feature | Decision |
|---|---|---|---|
| FR-1 | The orbit ingest DAG (an Airflow job, component C1) pulls CelesTrak GP data (orbital elements) as JSON no more than once per 2-hour update, and stops on any response other than HTTP 200 | F-1A.1 | Build plan 1A.1 |
| FR-2 | Every ingest job keeps each raw file unchanged, with its source URL, fetch time and hash | F-1A.1 and all sources | Engineering standard 1 |
| FR-3 | The Direct-to-Cell selector (C2) selects Direct-to-Cell satellites by the [DTC] tag in their names | F-1A.1 | ADR 0002 |
| FR-4 | The selector (C2) cross-checks each selected satellite against altitude (about 330 to 370 km) and inclination (43 or 53 degrees), and logs and lists every disagreement | F-1A.1 | ADR 0002 |
| FR-5 | The trail loader (C3) loads the NPS trail lines for Grand Canyon and samples one point every 50 meters along them | F-1A.2 | ADR 0004 |
| FR-6 | The terrain horizon engine (C4) computes, for each trail point, the terrain horizon (how high terrain rises in each compass direction, out to about 15 km) from the Copernicus 30-meter elevation model on AWS | F-1A.2 | ADR 0004 |
| FR-75 | The terrain horizon engine (C4) runs the horizon computation for many trail points at the same time in Spark | F-1A.2 | ADR 0004 |
| FR-76 | The terrain horizon engine (C4) stores the horizon of every trail point in Iceberg | F-1A.2 | ADR 0004 |
| FR-7 | The satellite window engine (C5) propagates the selected satellites with SGP4 (the standard orbit model) at 1-minute steps for 26 hours (24 hours plus the 2-hour nightly maximum), so the page has no daily gap. The 24 hours is the promise to the visitor, and the extra 2 hours are a safety margin; the page still says "the next 24 hours" | F-1A.3 | Build plan 1A.3; ADR 0019 |
| FR-8 | The satellite window engine (C5) counts a satellite as reachable from a trail point only when the satellite is above both 10 degrees and the terrain horizon in its direction | F-1A.3 | ADR 0003 |
| FR-9 | The satellite window engine (C5) stores satellite windows as start and end times per trail point, and never as one row per minute | F-1A.3 | ADR 0005 |
| FR-10 | The satellite window engine (C5) stamps each run with the time its predictions stop being valid, and a rerun of a day replaces only that day | F-1A.3 | ADR 0006 |
| FR-11 | The satellite window engine (C5) records in this project's design document how the satellite windows change at 5 and 20 degrees | F-1A.3 | ADR 0003 |
| FR-12 | The FCC coverage loader (C6) loads FCC mobile coverage (H3 resolution 9 files) for one carrier in Arizona and flags each trail point as covered or not | F-1A.4 | ADR 0007 |
| FR-13 | The dbt project (C7) builds staging, intermediate and a small star schema (trail point, time, coverage and satellite windows) on DuckDB; `source()` is used only in staging; unique and not_null tests are on keys | F-1A.5 | Engineering standard 6 |
| FR-14 | The project keeps a contract for CelesTrak, FCC, NPS trails and elevation, and the contract diff (C8) compares each source's schema with its contract before loading | F-1A.5 | ADR 0018 |
| FR-15 | The publish gate (C9, using Great Expectations) checks freshness, empty results and value ranges; new data lands in staging, passes the checks, and only then goes live | F-1A.5 | Engineering standard 4 |
| FR-16 | The publisher (C10) publishes the gold tables (the finished tables the page reads) as Parquet | F-1A.6 | Platform serving template |
| FR-17 | The trail page (C12) lets the visitor pick a trail and shows a strip map (bars where the carrier has coverage, no bars where it does not) and the next satellite windows along the trail, with credits | F-1A.6 | Build plan 1A.6 |
| FR-18 | The trail page (C12) shows "Predictions valid until [time]" in the hiker's local time. When the data is late or the run failed, the page still shows the old data with a visible late notice that includes the time of the last good run, and does not hide the data | F-1A.6 | ADR 0006 (amended) |
| FR-19 | The trail page (C12) states that Direct-to-Cell texting needs T-Mobile service (in the United States) and a supported phone, and that T-Mobile is the Phase A carrier | F-1A.6 | Build plan project description |
| FR-20 | The trail page (C12) shows the cold-start notice: "The first request after a period of inactivity may take up to 10 seconds while the service initializes." | F-1A.6 | Build plan 0.4, Decisions "Cold starts" |
| FR-21 | Every pipeline stores timestamps in UTC, and only the trail page converts them to local time | all | Engineering standard 15 |
| FR-22 | Every pipeline task is idempotent (safe to run again with the same result) and atomic (all or nothing): it overwrites a partition instead of appending blindly, and uses the run's data interval instead of the current time | all | Engineering standard 3 |
| FR-23 | Every pipeline writes event time and a source key on every record | all | Engineering standard 2 |
| FR-24 | Each DAG writes freshness and row counts to the metrics table | all | Platform step 0.5 |

### 4.2 Phase B

| ID | Requirement | Feature | Decision |
|---|---|---|---|
| FR-25 | The all-carrier loader (C13) loads FCC coverage for every carrier for the park into Iceberg | F-1B.1 | Build plan 1B.1 |
| FR-26 | The Ookla loader (C13) loads Ookla open mobile speed-test data for Arizona (quarterly, about 600-meter tiles, GPS-accurate tests only) into Iceberg | F-1B.1 | Build plan 1B.1 |
| FR-27 | The trail page and the README show the exact Ookla license notice (see AC-1B.1) | F-1B.1 | ADR 0013 |
| FR-28 | The nightly run publishes each new element set to Kafka. A Structured Streaming job (C14), run with the availableNow trigger, finds changed satellites and triggers re-propagation, using an explicit schema, checkpoints on S3, a watermark and dropDuplicatesWithinWatermark | F-1B.2 | ADR 0016 |
| FR-29 | A refresh step at the end of each pipeline run makes Snowflake see new Iceberg data through the Glue catalog | F-1B.3 | ADR 0015 |
| FR-30 | The dbt marts run on Snowflake, with SCD Type 2 rows (history kept as rows with validity ranges) for carrier coverage changes between FCC releases | F-1B.3 | ADR 0015 |
| FR-31 | The project defines its metrics in MetricFlow, provides a Superset dashboard, and publishes snapshot charts to the site each night | F-1B.3 | Build plan 1B.3 |
| FR-32 | A Snowflake resource monitor suspends the warehouse at 3 credits a month, and every query has a time limit | F-1B.3 | Decisions "Snowflake" |
| FR-33 | The platform runs OpenLineage with Marquez (an ARM build of one pinned version) and publishes the dbt docs catalog page | F-1B.3 | Platform |
| FR-34 | The confidence model (C17) predicts how likely the FCC map is to be right, using terrain, distance to the nearest tower (OpenCelliD, ADR 0024) and remoteness (distance to the nearest TIGER/Line road or NPS trail line, ADR 0024, ADR 0035) | F-1B.4 | ADR 0008 |
| FR-35 | The confidence model (C17) gives a confidence level only where enough speed tests exist nearby; elsewhere the page says "Not enough measurements here; the coverage map's claim is unverified." | F-1B.4 | ADR 0008 |
| FR-36 | John trains the model in Databricks (the data is uploaded through its Files API) and MLflow tracks every version | F-1B.4 | ADR 0014 |
| FR-37 | After each training run, John exports the results and the chosen model by hand (downloads them and commits them to GitHub; whether this can be automated is open, OQ-19). A small monthly job keeps the free Databricks account active. The nightly pipeline always scores with the copy in the repo. Check: after each training run, a results file that carries the run id is present in the repo | F-1B.4 | ADR 0014 |
| FR-38 | Every model call is logged to S3 (model, prompt version, tokens, latency, cost), and the nightly run loads the log into the `llm_calls` table | F-1B.5 | Build plan 1B.5 |
| FR-39 | The assistant traces every agent run with OpenTelemetry into AWS X-Ray | F-1B.5 | Decisions "Tracing" |
| FR-40 | An MCP server (a tool interface for AI models) exposes the metrics as tools; raw SQL is a read-only, allowlisted fallback that is logged separately | F-1B.5 | ADR 0017 |
| FR-41 | The project keeps prompts versioned in git, requires structured output on every model call, and uses only the cheapest model for now | F-1B.5 | Decisions "AI" |
| FR-42 | The project sets a daily question cap and the $10 monthly spend limit before the first model call | F-1B.5 | Decisions "AI spending" |
| FR-43 | The assistant answers a plain-language question with a check-in plan: where each carrier works, when satellite windows open, and how confident the map is, citing the trail points and times it used | F-1B.6 | ADR 0017 |
| FR-44 | The assistant says so when the data cannot answer the question | F-1B.6 | ADR 0017 |
| FR-45 | The eval suite has 30 or more questions with known answers, including ones the data cannot answer, and grades them exactly on tool choice, numbers and refusal | F-1B.7 | Build plan 1B.7 |
| FR-46 | An LLM judge (a second model) scores answer clarity, calibrated on 50 answers that John graded by hand | F-1B.7 | Build plan 1B.7 |
| FR-47 | The red-team set has 20 or more prompts covering instructions hidden in source text, write requests, off-topic requests and cost abuse | F-1B.7 | Build plan 1B.7 |
| FR-48 | The assistant stores thumbs-up and thumbs-down votes in DynamoDB, and the project A/B tests two prompt versions | F-1B.7 | Build plan 1B.7 |
| FR-49 | The trail page has "I had signal here" and "I had no signal here" buttons | F-1B.8 | Build plan 1B.8 |
| FR-50 | When the hiker taps a button, the phone reads GPS, converts it to an H3 resolution 9 cell with the h3-js library, and discards the exact coordinates on the phone | F-1B.8 | ADR 0009 |
| FR-51 | A report contains only the cell, the carrier, signal yes or no, and the time rounded to the hour | F-1B.8 | ADR 0009 |
| FR-52 | The phone saves a report and sends it automatically when signal returns (in the background on Android; on iPhone, the next time the page is opened, with a "1 report waiting to send" note) | F-1B.8 | ADR 0010 |
| FR-53 | The report API (Lambda, C22) writes each accepted report to DynamoDB | F-1B.8 | ADR 0012 |
| FR-54 | The phone creates a random visitor ID, and the report API (C22) identifies a visitor only by that ID; no internet address is used | F-1B.8 | ADR 0011 (amended) |
| FR-70 | The report API (C22) refuses a visitor's 11th report in a day (the limit is 10 reports a day per visitor) | F-1B.8 | ADR 0011 (amended) |
| FR-71 | The report API (C22) refuses a second report from the same visitor for the same cell within 24 hours | F-1B.8 | ADR 0011 (amended) |
| FR-72 | The report API (C22) counts each report toward the limits by the hour the report was made on the phone, not by its arrival time | F-1B.8 | ADR 0011 (amended) |
| FR-73 | The report API (C22) refuses reports beyond 50 a day for the whole system | F-1B.8 | ADR 0011 (amended) |
| FR-74 | The report API (C22) stores limit counters apart from the reports and lets them expire (lifetime: 72 hours after the UTC day, ADR 0026), so a report never carries an ID that links it to a visitor | F-1B.8 | ADR 0011 (amended) |
| FR-55 | DynamoDB deletes each raw report row 30 days after the nightly copy into the lake and Snowflake. The lake and Snowflake copies follow the same 30-day rule and keep daily per-cell counts (OQ-43, ADR 0034) | F-1B.8 | ADR 0012 |
| FR-56 | The nightly copy (C23) sets aside impossible patterns (reports outside any mapped area, bursts that contradict nearby reports) for review | F-1B.8 | ADR 0012 |
| FR-57 | The nightly copy (C23) turns reports into labels for the confidence model, including the missing no-signal cases, only where at least N reports in the same cell on the same day agree. Each of those reports is from a different visitor, because one report per cell per visitor is allowed every 24 hours (N is open, OQ-12). The model retrains once there are enough labels | F-1B.8 | ADR 0008, ADR 0012 |
| FR-58 | The trail page shows report counts per area | F-1B.8 | Build plan 1B.8 |
| FR-59 | The project applies these S3 clean-up rules (each rule deletes by age): dev data after 14 days; temporary files and Spark checkpoints after 7 days; failed partial uploads after 7 days; pipeline logs after 90 days; security logs (CloudTrail, including Parameter Store reads) after 1 year; old file versions after 30 days. Raw source files and published data are kept. An alarm fires if storage passes a set size | F-1B.9 | Decisions "Storage clean-up" |
| FR-60 | The project measures Lambda cold starts and reports the median warm latency and the 95th-percentile cold-start time in the README | F-1B.9 | Decisions "Cold starts" |
| FR-61 | A weekly smoke test (a small trial pull) pulls one small sample from every source and alerts on any format change | F-1B.9 | ADR 0018 |
| FR-62 | A failed run or a missed freshness target opens one GitHub issue, which is de-duplicated and closed on recovery | F-1B.9 | Build plan 1B.9 |
| FR-66 | The platform removes internet addresses from CloudFront and API Gateway logs before anything is stored beyond a short log retention period (kept 7 days, OQ-29, ADR 0029) | F-1B.8 | ADR 0023 |
| FR-67 | The OpenCelliD loader (C13) loads tower locations for the distance to the nearest tower; derived data carries the share-alike license, which is recorded in the license register and on the page | F-1B.4 | ADR 0024 |
| FR-68 | The assistant answers only within the prediction span and says so when asked about later days | F-1B.6 | ADR 0021 |
| FR-69 | The reports table has point-in-time recovery switched off, so deletion is final at 30 days; other tables keep it on | F-1B.8 | ADR 0022 |

### 4.3 Phase C

| ID | Requirement | Feature |
|---|---|---|
| FR-63 | The project covers every national park and accepts a GPX route upload | F-1C.1 |
| FR-64 | The project offers an offline trip pack (map, satellite windows and check-in plan saved to the phone) | F-1C.2 |
| FR-65 | The project compares the cheapest model with a stronger one in the eval suite and switches only if the scores justify the cost | F-1C.3 |

---

## 5. Quality requirements (arc42 section 10)

Every quality requirement has a measure and a verification method. Where the build plan or Decisions document records a number, it is used; where it does not, the number is an open question and the requirement says so. No number below is invented.

### 5.1 Quality scenarios

| ID | Quality | Scenario (stimulus, environment, response) | Measure | Verified by | Basis |
|---|---|---|---|---|---|
| QR-1 | Freshness | The nightly run executes every day at 10:00 UTC (3 a.m. Arizona, 6 a.m. US Eastern) | A run every day; usually about 45 minutes; hard maximum 2 hours; hitting the maximum is recorded as an incident | Status page shows each pipeline's last good run; Airflow run history; incident record | Decisions "Data freshness", "Nightly shutdown"; defaults table |
| QR-2 | Freshness | CelesTrak is requested | No more than once per 2-hour update | Unit test of the pull guard; DAG review | Build plan 1A.1 |
| QR-3 | Correctness (late data is labeled) | The nightly run fails and the page is opened after the previous predictions have expired | The page shows the old data with a visible late notice and the time of the last good run, and states "Predictions valid until [time]"; it does not hide the data. Definition of "late" is decided in ADR 0027 (OQ-23) | Front-end test with a controlled clock (late notice appears; data stays visible); manual check on the live page (AC-1A.6) | ADR 0006 |
| QR-4 | Correctness (data quality) | A source file arrives empty, stale or out of range | Publishing stops; nothing reaches the site | Great Expectations checks tested with small sample files in CI (AC-1A.5) | Build plan 1A.5 |
| QR-5 | Availability | A visitor opens the trail page while the session box is off | The page answers for every main trail | Test with the box off (AC-1A.6); Lambda runs DuckDB over published Parquet | Build plan 1A.6; platform serving template |
| QR-6 | Performance (cold start) | First request after a period of inactivity | The page says it may take up to 10 seconds; median warm latency and 95th-percentile cold-start time are measured and published in Phase B | Measurement in F-1B.9; README | Decisions "Cold starts" |
| QR-7 | Performance (targets) | Page latency, satellite window job duration | No numeric target is recorded. Satellite window job rows and runtime are measured on the session box (OQ-1) | Test run on the session box; limits set from the measurement | Documentation Plan "Questions still open" |
| QR-8 | Cost | A normal month | Under $50 a month, browser only; skeleton and Phase A months usually under $20 | Monthly cost review against the operating-model table; $40 AWS budget as backup | Decisions "Budget"; operating model |
| QR-9 | Cost (hard limits) | Any paid item | A Spark job over its maximum rows or runtime stops before publishing and opens an incident; Snowflake limited to 3 credits a month and a time limit on every query; AI at $10 a month with a daily question cap and a token limit per answer; DynamoDB provisioned within the free tier; session limit 4 hours; nightly maximum 2 hours. The row and runtime values per job, the daily cap and the token limit have no recorded values (OQ-15, OQ-17) | Job-level checks tested in CI with sample data; Terraform resources inspected; resource monitor inspected | Decisions "Surprise costs"; build plan "Hard limits" |
| QR-10 | Privacy | A hiker submits a report | The server receives no exact coordinates, only the H3 resolution 9 cell, carrier, signal yes or no and the time rounded to the hour; no internet address is used for identity; counters never link to stored reports | Request-capture test shows the payload; DynamoDB table inspection (AC-1B.8) | ADR 0009, ADR 0011 |
| QR-11 | Privacy (retention) | A raw report is 30 days past its nightly copy into the lake and Snowflake | The raw row is gone | DynamoDB expiry test (AC-1B.8). Point-in-time recovery is off for the reports table, so deletion is final (ADR 0022) | ADR 0012 |
| QR-12 | Licensing | Any page or README that shows derived data | Credits are shown; the Ookla notice is exact and present on the page and in the README; derived Ookla data carries the same license | Review checklist in the pull request; page text test for the Ookla notice (AC-1B.1) | ADR 0013; build plan 1B.1 |
| QR-13 | Security | Any key, role or deploy | Every key is in Parameter Store (the AWS key store) and none is in code or GitHub; one least-privilege IAM role (permission set) per pipeline; dev roles cannot write live data; gitleaks and Trivy scans in CI; source text treated as data, never as instructions; agents get read-only, allowlisted access | CI scans; role-refusal test from the platform skeleton; red-team set (FR-47) | Engineering standard 13; platform step 0.2 |
| QR-14 | Reliability (rerun safety) | A task is retried, a day is rerun, or AWS takes back a spot server (a cheaper server that can be reclaimed) | Rerunning a day replaces only that day; replaying a day of orbit updates writes the same rows | Re-run tests on sample data: running the same task twice gives the same result (AC-1A.3, AC-1B.2) | Engineering standard 3 |
| QR-15 | Reliability (spot) | Spot capacity unavailable at 10:00 UTC | The night is skipped; the next run catches up; the page shows the old data with the late notice | Platform skeleton checks; QR-3 | Decisions "Nightly shutdown"; operating model |
| QR-16 | Observability | A run fails or misses its freshness target | An email is sent and an incident record is written; in Phase B one de-duplicated GitHub issue opens and closes on recovery | First real failure (platform step 0.5); smoke test in F-1B.9 | Platform step 0.5; build plan 1B.9 |
| QR-17 | Honesty of coverage claims | A trail point has too few nearby speed tests | The page says "Not enough measurements here; the coverage map's claim is unverified." and shows no confidence level | Test with a sparse-area fixture (AC-1B.4) | ADR 0008 |
| QR-18 | Honesty of AI answers | The assistant states a number | The number appears in the query result; otherwise the harness fails | Eval harness (AC-1B.5) | Build plan 1B.5 |
| QR-19 | Assistant quality | CI runs the eval suite | CI fails below its accuracy and red-team thresholds. The threshold values are not recorded (OQ-16) | Evals in CI (AC-1B.7) | Build plan 1B.7 |
| QR-20 | Data-contract integrity | An upstream source changes format | The change fails loudly and early: schema diff before loading; weekly smoke test in Phase B | Contract diff test in CI with sample files; weekly smoke test | Engineering standard 5; ADR 0018 |
| QR-21 | Time handling | Any timestamp | Stored in UTC; converted to local time only on the page | Unit test of the conversion; schema check that stored columns are UTC | Engineering standard 15 |
| QR-22 | Lineage and docs | A reviewer inspects the models | The lineage graph shows every step from raw to gold tables; the dbt docs are published | Marquez graph and docs page (AC-1B.3) | Build plan 1B.3 |

### 5.2 Constraints that shape the requirements

| Constraint | Value | Basis |
|---|---|---|
| Monthly budget | Under $50, browser only | Decisions "Budget" |
| Phase A scope | Bright Angel, South Kaibab and North Kaibab, T-Mobile, next 24 hours (26 predicted) | ADR 0001, 0019, 0020 |
| Non-commercial licenses | Ookla (CC BY-NC-SA 4.0) and Databricks Free Edition are non-commercial; OpenCelliD is share-alike; licensing must be checked before charging | Build plan "Assumptions" |
| Test method | Small sample files in CI; no staged production failures | Decisions "Failure testing" |

---

## 6. Acceptance criteria per feature

These are the build plan's "Done when" checks. They are reproduced without change; the mapping to functional requirements is the right-hand column.

### 6.1 Phase A

| Feature | Acceptance criterion (Done when) | Requirements |
|---|---|---|
| F-1A.1 | AC-1A.1: Raw files land with hash and load time, and the selection is unit-tested, with disagreements listed. | FR-1 to FR-4 |
| F-1A.2 | AC-1A.2: Every trail point has a horizon profile, and a canyon-floor point shows a much higher horizon than a rim point. | FR-5, FR-6, FR-75, FR-76 |
| F-1A.3 | AC-1A.3: Every trail point has its satellite windows for the next 24 hours with a valid until time, and rerunning a day replaces only that day. (The run predicts 26 hours, ADR 0019; the criterion text is the build plan's.) | FR-7 to FR-11 |
| F-1A.4 | AC-1A.4: Every trail point has a coverage flag for the carrier. | FR-12 |
| F-1A.5 | AC-1A.5: dbt tests and check tests pass in CI, and publishing stops when a check fails. | FR-13 to FR-15 |
| F-1A.6 | AC-1A.6: The public link answers for every main trail with the box off, late data shows a visible late notice with the time of the last good run, and the README states exactly what is deployed. (Decided by John, Oct 9, 2026: the build plan's wording "expired satellite windows disappear on their own" is superseded; the late notice replaces it, ADR 0006.) | FR-16 to FR-20 |

Notes on measurability (open, not guessed): "much higher" in AC-1A.2 has no numeric threshold in the build plan; the test fixture compares a canyon-floor point and a rim point, and the numeric margin is 5 degrees between the medians of the canyon and rim fixtures (ADR 0036, OQ-24). The main trails are Bright Angel, South Kaibab and North Kaibab (ADR 0020); their names are checked against the NPS data in the first-run download (OQ-36).

### 6.2 Phase B

| Feature | Acceptance criterion (Done when) | Requirements |
|---|---|---|
| F-1B.1 | AC-1B.1: Coverage for every carrier and measured tiles are in Iceberg, and the license notice is on the page and in the README. The notice reads: "Includes data derived from Speedtest by Ookla® open data, licensed under CC BY-NC-SA 4.0. Derived data published here is shared under the same license." | FR-25 to FR-27 |
| F-1B.2 | AC-1B.2: Replaying a day of updates writes the same rows. | FR-28 |
| F-1B.3 | AC-1B.3: The marts pass their tests on Snowflake, one metric gives the same value from Snowflake and from DuckDB, and the lineage graph shows raw to gold. | FR-29 to FR-33 |
| F-1B.4 | AC-1B.4: MLflow shows the compared versions with their accuracy, the chosen model and its results are in the repo, and the trail page shows a confidence level where tests are dense enough and the "not enough measurements" notice elsewhere. | FR-34 to FR-37 |
| F-1B.5 | AC-1B.5: A test question runs end to end through the metrics tool, shows as a trace with its cost, and the harness fails when an answer states a number that is not in the query result. | FR-38 to FR-42 |
| F-1B.6 | AC-1B.6: Ten sample trip questions get correct, cited plans, checked by hand. | FR-43, FR-44 |
| F-1B.7 | AC-1B.7: CI fails below its accuracy and red-team thresholds, (the threshold values are open, OQ-16), and the README shows the scores, the judge's agreement with your grades and the A/B result. | FR-45 to FR-48 |
| F-1B.8 | AC-1B.8: A report made in airplane mode is saved and sends once the phone is back online, the server never receives exact coordinates, an 11th report in a day from one visitor is refused, the system refuses reports beyond 50 a day, (Decided by John, Oct 9, 2026: the build plan's wording "an 11th report in an hour is refused" is superseded by the per-day limits of ADR 0011) raw rows expire on schedule, and report counts per area are on the page. | FR-49 to FR-58, FR-66, FR-69 to FR-74 |
| F-1B.9 | AC-1B.9: The clean-up rules show on every bucket, warm and cold-start latency are in the README, the weekly smoke test runs, and the next real failure opens one issue. | FR-59 to FR-62 |

### 6.3 Phase C

No "Done when" checks are recorded for Phase C. The platform rule for the second round is that each project's design note is updated with measured numbers (build plan, "Build order and checkpoints"; the design note is this project's design document). Detailed criteria are a recorded gap: they are written when Phase C is designed (Decided by John, Oct 9, 2026).

---

## 7. Traceability

| Requirement group | Design doc section | ADR | Interface spec |
|---|---|---|---|
| Orbit ingest and selection (FR-1 to FR-4) | 7 (C1, C2), 8.1 | 0002, 0018 | contracts/celestrak_gp.yaml |
| Trails and terrain (FR-5, FR-6) | 7 (C3, C4), 7.A | 0004 | contracts/nps_trails.yaml, copernicus_glo30.yaml, contracts/trail_point_horizon.yaml |
| Windows (FR-7 to FR-11) | 7 (C5), 7.B | 0003, 0005, 0006 | contracts/fct_satellite_window.yaml |
| Coverage (FR-12, FR-25, FR-26) | 7 (C6, C13) | 0007, 0013 | contracts/fcc_mobile_coverage.yaml, ookla_open_data.yaml, contracts/fct_trail_point_coverage.yaml |
| Checks and publish (FR-13 to FR-16) | 7 (C7 to C10) | 0018 | all contracts |
| Page and API (FR-17 to FR-20) | 7 (C11, C12), 10 | 0006, 0019, 0020 | openapi.yaml |
| Streaming (FR-28) | 7 (C14) | 0016 | none (internal topic) |
| Warehouse (FR-29 to FR-33) | 7 (C15, C16) | 0015 | contracts/* |
| Confidence (FR-34 to FR-37, FR-67) | 7 (C17) | 0008, 0014, 0024 | contracts/fct_coverage_confidence.yaml |
| AI and assistant (FR-38 to FR-48) | 7 (C18 to C20) | 0017 | ../Platform/contracts/llm_calls.yaml, openapi.yaml |
| Reports (FR-49 to FR-58) | 7 (C21 to C23) | 0009 to 0012 | contracts/hiker_signal_reports.yaml, contracts/fct_report_counts_area.yaml, openapi.yaml |
| Operations (FR-59 to FR-62) | 7 (C24), 12 | 0018 | none |

Platform requirements that this project relies on are in [../Platform/platform-requirements.md](../platform/platform-requirements.md). They are not repeated here.
