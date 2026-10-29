# Project 1 changelog

This file records two things: changes to the documents, and, once code exists, changes to each phase of the project. The newest entry is first.

---

## Oct 9, 2026: defaults confirmed

- John confirmed ADRs 0025 to 0033 (visitor ID, day boundary, late-data rule, refresh and time grain, limits, area counts, model family, versions, votes). Their status is now Accepted.

## Documents

### Oct 29, 2026: trail_point contract

- New `contracts/trail_point.yaml`, approved by John: the internal Iceberg table C3 writes and C4 and C5 read. Before this it was declared only in code. The design doc's table list, C3's contract row and the requirements trace now point to it.
- The point key is `trail_point_id` (was `point_id` in the `TrailPoint` class), the same name as in `dim_trail_point` and every table built from it (OQ-21).

### Oct 28, 2026: Phase A first-run checks

The checks ran on John's laptop. Downloads were kept outside the repository. Answers are in design doc section 16.

- OQ-6 answered: 636 of 637 `[DTC]` satellites pass the altitude and inclination cross-check. The exception, STARLINK-11075 (58706), is at about 296 km and stays selected with a logged disagreement (ADR 0002).
- OQ-8 answered: the NPS trails for `GRCA` and the four Copernicus GLO-30 tiles download and open, and decoded heights match known points.
- OQ-36 answered: Bright Angel, South Kaibab and North Kaibab are one line each. The loader must match the whole `TRLNAME`.
- OQ-7 partly answered: the T-Mobile Arizona 4G LTE hexagon GeoPackage is 83 MB zipped, 289 MB unzipped, 1,007,438 rows. Ookla and OpenCelliD sizes are Phase B.
- OQ-20 partly answered: URLs, field lists, the `GRCA` unit code and the FCC file name pattern for the four Phase A sources. Ookla and OpenCelliD are Phase B.
- New open question OQ-44: which FCC rows count as covered for a hiker (environment and signal fields).
- Files checked, with SHA-256 hashes:

| File | Source | Size | SHA-256 |
|---|---|---|---|
| Starlink GP JSON, pulled 2026-10-28 02:44 UTC | celestrak.org | 4,715,590 bytes | not kept; it changes every pull |
| `grca_trails.geojson` (`UNITCODE='GRCA'`, all fields) | mapservices.nps.gov | 5,892,096 bytes | `d96a5ed47a2f939217e30e3cd5987dbe2cc3445a5069dd0e7f2548a8a88eb268` |
| `Copernicus_DSM_COG_10_N35_00_W113_00_DEM.tif` | copernicus-dem-30m (AWS Open Data) | 37,969,615 bytes | `5103c75c674fd6924a898203488f7761404b684a47d5e9e2e6fd3adcff2fb04a` |
| `Copernicus_DSM_COG_10_N35_00_W112_00_DEM.tif` | same | 37,529,476 bytes | `105a2ff831e660c878bb72ac88147c79659444167ef8931b5b4d4eeefc54b4b1` |
| `Copernicus_DSM_COG_10_N36_00_W113_00_DEM.tif` | same | 40,201,504 bytes | `3778b88efb81c8f05aa483d1d5267c07c55e058f34df6603f29be0ac99289e7b` |
| `Copernicus_DSM_COG_10_N36_00_W112_00_DEM.tif` | same | 39,364,241 bytes | `92df94da758bde3c9da71db304967893ae63b01f7bf314cca5ea07c73ac4e26e` |
| `bdc_04_130403_4GLTE_mobile_broadband_h3_D25_19oct2026.zip` | broadbandmap.fcc.gov | 82,984,558 bytes | `95701de37cfc89571178f332e16e23caec9eda50030a421fc19403eac1df4464` |

### Oct 28, 2026: documents approved

- John approved the requirements, the design doc, the ADRs, the data contracts and the API specification. This meets the gate in README section 9, so coding of Phase A can begin.
- Status lines changed from "Draft" to "Approved by John (Oct 28, 2026)" in README.md, requirements.md, design-doc.md and openapi.yaml, and in the header of every contract. Each contract's `status` field changed from `draft` to `active`, the ODCS (Open Data Contract Standard) term for a contract in force.
- Approval does not settle the open questions. Source URLs and field lists stay unconfirmed until the first-run checks (OQ-20, ADR 0018), and names stay working names (OQ-21).

### Oct 9, 2026: horizon defaults, credit wording, assistant spend limit

- OQ-24 (horizon details) is decided in ADR 0036: 15 km range, 30 m ray step, 1.7 m eye height, Earth curvature applied, refraction not applied, the surface model kept, 36 sectors final, linear interpolation, and a 5-degree margin for AC-1A.2.
- OQ-22 (credit wording) is decided in ADR 0037. Copernicus and NPS were checked against their own licence and policy text. CelesTrak has no terms, so a courtesy credit is used. OpenCelliD and FCC mobile data are unverified, because their primary pages returned HTTP 403 from the build environment. The page wording that coverage is a claim, and that satellite texts are not guaranteed, is also set there.
- OQ-17 is decided in ADR 0038 by John: a monthly spend limit of $10, replacing $15 everywhere in the set. Derived limits: 20 questions a day, 2,500 input and 800 output tokens per answer, with a price check before the first call.
- New contract: none in this step. The licence register and the credit wording were updated.
- Open questions: 19 open and 1 partly answered (OQ-39). ADRs total 39.

### Oct 9, 2026: remoteness source, report-cell contract, and the state of open questions

- Remoteness (OQ-18) is decided by John: U.S. Census TIGER/Line roads plus NPS trail lines (ADR 0035). Before the first load, the licence of the exact Census vintage must be checked, because some files carry a rights flag, "otherRestrictions". The check is a first-run check.
- New contracts: `tiger_roads` (the road source for remoteness) and `report_cell_day` (the daily per-cell counts that replace raw reports after 30 days, ADR 0034). Contracts now total 21.
- New internal table in the design doc: `trail_point_remoteness`. New lake table: `tiger_road`.
- Glossary and the licence register gained the Census source and the remoteness term.
- Open questions: 16 answered, 1 partly answered (OQ-39, the provider's terms), and 22 open. The 22 open ones need measurements, real files or accounts, or a decision that only John can make (thresholds, caps, N, attribution wording). Each has a GitHub issue still to be created.
- ADRs total 36 (0001 to 0035, with 0006a superseded).

### Oct 9, 2026: minor open questions decided (security first)

John asked for minor questions with an obvious best-practice answer to be decided, security first, and for major ones to be left for him. Thirteen questions were decided this way. Each has an ADR (0025 to 0033) marked as a default that John can change. Each answered row in design doc section 16 keeps its question and gains its answer, so existing references still resolve.

- Decided: OQ-11, OQ-21 (names accepted as working names), OQ-23, OQ-25, OQ-26, OQ-28, OQ-29, OQ-30, OQ-32, OQ-33, OQ-35, OQ-38, OQ-41. Partly decided: OQ-18 (model family) and OQ-39 (votes and question text).
- Decided by John, Oct 9, 2026 (ADR 0034): AWS region us-east-1 (OQ-42); report copies deleted 30 days after the copy in every store, with daily per-cell counts kept (OQ-43); model provider the Anthropic API on the cheapest Claude model (OQ-39, partly).
- New ADRs: 0025 visitor ID; 0026 day boundary and counter lifetime; 0027 late-data rule; 0028 reference refresh, stream and time grain; 0029 limits, retention and log window; 0030 area counts; 0031 confidence model family and carriers; 0032 pinned versions; 0033 votes and assistant data.
- Affected text was updated in the requirements, the design doc, ADRs 0001, 0008, 0011, 0016, 0018, 0020, 0022 and 0024, the contracts, the API file, the security document, the operations document and the model card.

### Oct 9, 2026: review pass before coding

Every item below was checked against the build plan, the Build Plan Decisions, the answered decisions and the open-question log.

**Added**
- [README.md](README.md): what the project is, the document map, the reading order, the build order by dependency and the accounts needed.
- [../Platform/platform-requirements.md](../platform/platform-requirements.md): the platform parts Project 1 depends on, so the project can be built from the documents alone.
- [operations.md](operations.md): schedules, freshness targets, monitoring, cost, 17 runbooks, incidents and backups.
- [security-and-privacy.md](security-and-privacy.md): threat model, personal-data inventory with retention, access matrix, licence and attribution register.
- [model-card.md](model-card.md): the confidence model and the trip assistant, with the evaluation plan and known failure cases. No results are claimed.
- This changelog.

**Changed**
- ADR 0006 existed twice. The superseded version (0006a) was removed on Oct 9, 2026 as a duplicate old version. The amended version keeps the number 0006.
- ADR 0005 said the window run covered 24 hours. It now says the 26-hour prediction span (ADR 0019).
- ADR 0011 and ADR 0022 said the limit counters expire after 24 hours. The build plan gives that value. Whether it covers the offline delay is open (OQ-26).
- ADR 0012 now says the 30-day rule covers DynamoDB only. The lake and Snowflake copies are open (OQ-43).
- ADR 0023 had a stray reference to another project's step. Removed.
- All 19 data contracts now have a server with a concrete storage location. Eleven contracts had `TBD`, and eight had no server block. The naming convention is in [design-doc.md](design-doc.md), section 9.1.
- The design doc, requirements and API specification now link to [../Platform/platform-requirements.md](../platform/platform-requirements.md) instead of placeholder paths to a platform folder that does not exist.
- The design doc gained: section 9.1 (storage names); section 10 (error codes, and a note that the vote endpoint's 429 has no recorded limit); section 14 (a table of where decisions changed the build plan); section 12.2 (a proposed rule that access logs exclude the visitor ID header); and open questions OQ-42 (AWS region) and OQ-43 (retention of report copies). OQ-39 was extended to cover vote limits.
- Glossary: duplicate entries removed; ODCS, residual risk, runbook and threat model added.
- Requirements: typos in the feature name "satellite window" corrected; FR-55 notes the open retention question.

**Not changed**
- Requirements, the 17-section design doc structure, the 24 ADRs, the 19 contracts' schemas, and the API paths and operations. These were already complete.
- The root-level files `ANSWERED_DECISIONS.md` and `DECISIONS_NEEDED.md`. Each Project 1 item in `DECISIONS_NEEDED.md` is either answered in the design doc or narrowed to an open sub-question (design doc, section 16). Answers come from `ANSWERED_DECISIONS.md`.

**Still open at this revision**
- 24 open questions remain, counting the two partly decided ones (OQ-18 and OQ-39). Each has a GitHub issue still to be created.
- The platform's own document set (not written).
- The reference generated from code (written when the code exists).
- John's approval of each document.

### Oct 9, 2026: first complete set

- Requirements (76 functional requirements, 22 quality requirements, acceptance criteria for every feature in Phases A and B).
- Design doc, 17 sections, following the design doc template in the Documentation Plan.
- ADRs 0001 to 0024.
- Data contracts (ODCS v3.0.2 working version) for the 19 published, source and internal tables.
- API specification (OpenAPI 3.0.3 working version) with six operations.
- Status: draft for review.

---

## Phases

### Oct 29, 2026: declared lake column types (code)

- `pipelines/signal/lake_write.py` gives Spark each table's column types from its contract instead of letting Spark guess them. A guess failed the live skeleton run on 2026-10-29 (INC-2026-10-29-01), cannot type a column that is empty in every row, and can make a number column an integer one night and a double the next.
- Rows are checked before Spark sees them: a missing or extra column, or an empty required one, stops the load with the column's name. Whole numbers in number columns become floats; times and the run date become plain UTC types.
- `load_gp_partition` takes the `celestrak_gp` contract path; `load_trail_tables` takes the `nps_trails` and `trail_point` contract paths.

### Oct 28, 2026: C3 trail loader (code)

- `pipelines/signal/trail_loader.py`: pages through the NPS Public Trails service for `GRCA` in OBJECTID order (2,000 a page), stopping on any status other than 200, an error inside a 200 or more than 10 pages; keeps each page unchanged with a manifest under `signal/nps/trails/unitcode=GRCA/fetched_at=<time>/`; checks the fields against the contract (C8); keeps Bright Angel, South Kaibab and North Kaibab by whole name, each required to be exactly one line in one part; places a point every 50 m measured along the line, plus the line's last point; writes `nps_trail_line` and `trail_point` for the run date.
- Conventions (working names, OQ-21): trail IDs are slugs such as `grca-bright-angel`, because OBJECTID can change when the NPS republishes; point IDs add a five-digit sequence from 0, such as `grca-bright-angel-00042`. Elevation is added by C4.
- On the real file from the first-run check: 12.68, 10.41 and 23.26 km, and 255, 210 and 467 points (932 in all).
- Contract `nps_trails` 0.2.0: confirmed URL and raw location, `upstreamField` and `upstreamType` for OBJECTID, TRLNAME and UNITCODE, and `geometry_geojson` stored as GeoJSON text.
- Shared helpers: `raw_store.py` (download and keep a raw file with its manifest) and `lake_write.py` (write a run-date partition) now serve C1 and C3; C1's behavior is unchanged and its tests still pass.

### Oct 28, 2026: C2 Direct-to-Cell selector (code)

- `pipelines/signal/dtc_selector.py`: `select_dtc_satellites` keeps every satellite whose name carries `[DTC]` and cross-checks each one. The exact rule (ADR 0002 left it to the code): perigee and apogee both between 330 and 370 km, from mean motion and eccentricity above the equatorial radius, and inclination within 0.5 degrees of 43 or 53. A disagreement is logged and listed; the satellite stays selected. No tagged satellite at all stops the run.
- On the real file from the first-run check: 637 selected, 2 disagreements. STARLINK-11075 (58706) is low (perigee 294 km); STARLINK-11434 (62420) has an apogee of 379 km, so its orbit is not yet circular even though its mean altitude is in the band. The OQ-6 check used mean altitude, so it found only the first.
- Not yet written to the lake: the `dtc_satellite` and `dtc_disagreement` tables come with the nightly DAG change.

### Oct 28, 2026: C1 orbit ingest (code)

- `pipelines/signal/orbit_ingest.py`: `fetch_gp_json` pulls the confirmed CelesTrak URL, refuses a second pull within 2 hours without calling CelesTrak, and stops on any status other than 200 or an empty body; `store_raw` writes the file unchanged and a manifest (URL, fetch time, size, SHA-256) under `signal/celestrak/gp/fetched_at=<time>/` in the raw bucket, never replacing a file; `parse_gp_records` runs the contract diff (C8) before anything is loaded; `lake_rows` renames fields to the contract columns; `load_gp_partition` writes one Iceberg partition per run date. Checked on the real file from the first-run check: all 11,133 records pass.
- Contract `celestrak_gp` 0.2.0: the confirmed upstream field names, their JSON types (`upstreamType`) and the confirmed URL and raw location.
- C8: whole numbers in a number field are not a type change, because JSON writes 0.0 as 0.
- Not yet in the nightly run: the `orbit_ingest` DAG, the raw bucket setting on the box, and the image copy of `pipelines/signal` come in a separate change.

### Oct 28, 2026: C8 contract diff

- `pipelines/signal/contract_diff.py` reads the source fields a contract names in `upstreamField` (with the source type in `upstreamType` when given) and compares them with a source file's fields. A removed field or a changed type stops the run and names the field; a rename shows as removed plus added; an added field is listed only. Tests: `pipelines/signal/tests/test_contract_diff.py`.
- Not yet wired into a DAG or the metrics table: that comes with C1, the first source it checks.

| Phase | Status | Released |
|---|---|---|
| Platform skeleton (before Project 1) | Built; first unattended live run on 2026-10-28 | Live |
| Phase A: live (Grand Canyon, T-Mobile, next 24 hours) | In progress: C8, C1, C2 and C3 code built; not yet in the nightly run | Not released |
| Phase B: depth (every carrier, warehouse, confidence model, assistant, reports) | Not started | Not released |
| Phase C: scale (second round) | Not started. Acceptance checks not yet written | Not released |

Entries for each phase are added here when the phase ships. Each entry lists the features that went live, the checks that passed, and any known gaps.
