# Project 1 changelog

This file records two things: changes to the documents, and, once code exists, changes to each phase of the project. The newest entry is first.

---

## Oct 9, 2026: defaults confirmed

- John confirmed ADRs 0025 to 0033 (visitor ID, day boundary, late-data rule, refresh and time grain, limits, area counts, model family, versions, votes). Their status is now Accepted.

## Documents

### Nov 10, 2026: Ookla contract approved

- John approved contract `ookla_open_data` 0.2.0. It is now active.

### Nov 10, 2026: Ookla first-run check (OQ-10)

- The Ookla 2026 quarter 3 mobile file was read on the laptop (kept outside the repository): 189,644,612 bytes, MD5 f22f98824d61cd039c2cd57d3dea69b8, matching the bucket's ETag. OQ-10 is answered; OQ-2, OQ-7 and OQ-20 are partly answered.
- Contract `ookla_open_data` 0.2.0 is proposed and waits for John's approval: the real file location, the field names, `tile_key` is the quadkey, explicit speed and device columns replace `speed_metrics`, and a note that a tile mixes every carrier.
- C13 drops `filter_gps_accurate`, because Ookla publishes only tests with GPS-quality locations. C17 notes that Ookla evidence is not per carrier.

### Nov 10, 2026: report contracts approved

- John approved contracts `signal_report` 0.1.0 and `hiker_signal_reports` 0.2.0. Both are now active.

### Nov 9, 2026: nightly report copy (C23, part 1)

- John decided the FR-56 set-aside rules: more than 10 km from every Phase A trail point is outside the mapped area; a cell and hour with 3 or more reports holding both answers is a contradicting burst. Recorded in the C23 design.
- The C23 design has an "As built, part 1" row. New contract `signal_report` 0.1.0 and `hiker_signal_reports` 0.2.0 (table names, the cell counter fields, recovery off for the counters) are proposed and wait for John's approval.

### Nov 9, 2026: report buttons (C21, part 1)

- The C21 design now has an "As built, part 1" row: the two report buttons on the trail page, a carrier picker, the H3 cell computed on the phone with h3-js, and a queue on the phone that sends when the page is open. Sending in the background on Android (a service worker) is part 2.

### Nov 9, 2026: report API (C22)

- The C22 design now has an "As built" row: its own function on `POST /reports`, two DynamoDB tables with provisioned capacity in the free tier, one transaction per report, and the visitor ID and place kept only as keyed hashes in the counters. ADR 0029's reserved concurrency of 10 is not set, because the account's whole Lambda limit is 10.

### Nov 5, 2026: site redesign

- John approved a new look for the site. The trail tool is now the home page, and the old home text is at `/about`. The strip map became a trail map on real terrain, with a key, so FR-17, F-1A.6 and the C12 design now say trail map.
- `pipelines/signal/trail_terrain_art.py` draws each trail's terrain picture and height list by hand from the GLO-30 tiles. It is not part of the nightly run. The trail photos come from Wikimedia Commons, and each is credited beside the photo.
- The lookup page stays at `/lookup` because PR-12 names it, but it is no longer in the navigation.

### Nov 5, 2026: Phase A deployed

- C12 built and deployed. The README states what is live. Box runtime recorded in OQ-1 and section 7.B.

### Nov 5, 2026: C11 built

- GET /trails and GET /trails/{trail_id}/signal read the published files. `WindowOut` in openapi.yaml no longer has `satellite_id`: a window is now a reachable period (John's choice).

### Nov 5, 2026: reachable periods

- Every window of a trail would not fit in one API answer: 984,227 windows on North Kaibab against Lambda's 6 MB limit. John chose to merge overlapping windows into reachable periods per point: 20,956 on North Kaibab.
- New mart `fct_reachable_period` and contract 0.1.0 (proposed). `fct_satellite_window` stays published with the detail.

### Nov 5, 2026: C9 and C10 built

- John chose the existing publish gate over Great Expectations for Phase A, and set the gate's limits (OQ-15). FR-15, F-1A.5 and design doc C9 changed.
- C10 publishes one Parquet file per mart. `fct_satellite_window` is 7.5 MB, so it is not split by trail.

### Nov 5, 2026: elevation removed from dim_trail_point

- Contract `dim_trail_point` 0.2.0: John removed `elevation_m`. No step stored it, and neither the API nor the page reads it. It can come back when something needs it.

### Nov 4, 2026: OQ-40 decided and C7 built

- OQ-40 answered by John: Spark copies the needed partitions to plain Parquet, and dbt reads those.
- Design doc C7 now lists the models as built, and dbt's own Python environment.
- Contract `trail_point_coverage` 0.1.0 approved by John: status active.

### Nov 4, 2026: OQ-44 decided and C6 file reader

- John decided OQ-44: every cell listed in the FCC file counts as covered. Contract `fcc_mobile_coverage` 0.2.0 stores `environment` and `min_signal_dbm` on each cell, so the rule can change without loading the file again.
- `pipelines/signal/fcc_coverage.py` reads the GeoPackage with the standard library and refuses another provider's file, another state's file, an empty file and a repeated cell. `flag_points_covered` gives each trail point a covered flag. On the real Arizona file it read 1,007,438 cells in about 7 seconds.
- `load_coverage_if_changed` and the DAG task `load_coverage` (after `load_trails`) write `fcc_coverage_cell` and `trail_point_coverage`, only when the kept file or the trail points changed (ADR 0028). The FCC site refuses automated requests, so the file is put in the raw bucket by hand with a manifest. New dependency `h3` 4.5.0.
- On the real Arizona file, 436 of 932 trail points are covered. Contract `trail_point_coverage` 0.1.0 is proposed.

### Nov 4, 2026: satellite window engine (C5)

- New internal contract `contracts/satellite_window.yaml` (proposed, waiting for John): the columns of `fct_satellite_window`, with `run_date` as the partition column like the other internal tables. The nightly DAG gets a `compute_windows` task after `select_dtc` and `compute_horizons`.
- Design doc table 7.B now lists the functions as built: `SatelliteTrack` (one array per satellite) replaces the per-minute `SatellitePosition`, and `minute_times`, `teme_positions`, `teme_to_ecef` and `windows_for_point` are new. `find_windows` keeps its name and takes a point and a track. A satellite counts as reachable at or above the minimum elevation and strictly above the terrain.
- Section 7.B records the measured size from the Nov 4 live tables, and OQ-1 and OQ-9 say what is answered: about 2.16 million windows a night at 10 degrees, with the 5 and 20 degree comparison. The choice of 10 degrees stays John's.
- John set the satellite window row limit to 4,000,000 (OQ-1): about twice the measured 2,156,029, so the constellation can grow but a doubling bug stops the run before anything is written.

### Nov 4, 2026: own domain

- The live link is now https://signal.johnwasikye.com. The site moved there in two steps: first the HTTPS certificate, then the domain itself. The cloudfront.net address still works.

### Nov 4, 2026: status and live link

- The README's status line says which Phase A components are built, and the live link points to the site, which is up with an "Under development" banner. The repository README now describes what is deployed.

### Nov 3, 2026: terrain horizon engine (C4)

- New ADR 0038 (proposed, waiting for John): each sector's horizon is the highest of 10 rays one degree apart, angles below the level line are stored as 0, heights come from the nearest grid cell, and the tiles are read by a small GeoTIFF reader instead of rasterio (John's choice).
- Design doc table 7.A now lists `ElevationGrid` and `read_elevation_grid` (`geotiff.py`), `ElevationTiles` built from grids, and `load_elevation_tiles(paths)`. `ray_elevation_profile` is not a separate function: all rays are sampled at once. `HorizonProfile` and `Window` use `trail_point_id` (were `point_id`).
- `contracts/trail_point_horizon.yaml` 0.2.0: the angle array declares its items as numbers, and points to ADR 0036 and 0038 instead of the closed OQ-24. The `signal_phase_a_nightly` DAG gains `compute_horizons` after `load_trails` (C4 runs when the newest trail points have no horizon yet). The GLO-30 tile manifest is kept under `signal/copernicus/manifest/` in the raw bucket.

### Oct 29, 2026: contracts for the Direct-to-Cell tables

- New `contracts/dtc_satellite.yaml` and `contracts/dtc_disagreement.yaml`, approved by John: the internal Iceberg tables C2 writes. The design doc said their schema lived in code; every lake table now has a contract, as `trail_point` does. The design doc's C2 contract row and table list point to them.
- The Phase A DAG is `signal_phase_a_nightly` (proposed as `orbit_ingest`), because it runs C1, C8, C2 and C3 together (OQ-21).

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

### Oct 29, 2026: Phase A nightly DAG (code)

- `pipelines/signal/dags/signal_phase_a_dag.py` (`signal_phase_a_nightly`, 10:00 UTC): pull CelesTrak, check the file against its contract (C8), load `celestrak_gp`, then select the Direct-to-Cell satellites into `dtc_satellite` and `dtc_disagreement`. The trail load runs beside them. Every task tries twice more, then records an incident and sends an email.
- `pipelines/signal/signal_nightly.py` holds the steps. A CelesTrak pull from the last 2 hours is reused, so a retry never pulls twice. Every step reads the raw file the pull kept. Trails are kept and loaded only when the NPS pages differ from those the last load came from (ADR 0028). A night with no disagreement clears that night's partition of `dtc_disagreement`.
- Airflow reads DAGs from all of `pipelines/`; `pipelines/.airflowignore` keeps it to each project's `dags/` folder. The watchdog waits for both nightly DAGs.
- Not yet on the box: it takes effect after a reinstall.

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
