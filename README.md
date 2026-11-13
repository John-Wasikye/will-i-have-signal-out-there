# Will I have signal out there?

I am building a trip planner for hikers, campers and backpackers. You pick a trail and see where each phone carrier has coverage, where it drops out, and when a Starlink Direct-to-Cell satellite text could get through. This repository holds the data platform behind the planner and the planner's code.

The site is live at **https://signal.johnwasikye.com**, with an "Under development" banner on every page. Phase A is deployed: for Bright Angel, South Kaibab and North Kaibab at Grand Canyon, the trail page shows where the FCC data says AT&T, T-Mobile and Verizon have coverage, and when a satellite is predicted to be reachable, for the next 24 hours. I have not checked these predictions in the field, so please do not rely on them for your safety.

## What I have built

Everything runs on AWS in two separate environments, dev and live, built with Terraform and deployed by GitHub Actions.

| Part | Folder | Status |
|---|---|---|
| Serving API (FastAPI, DuckDB over Parquet, on Lambda behind API Gateway) | `platform/serving` | Live |
| Site (Vite, React, TypeScript, on CloudFront) | `app` | Live, with the development banner |
| Session box: an on-demand server that boots each night and runs Airflow and Spark on k3s, then stops | `platform/box` | Live. Saves the Airflow database to S3 before it stops. It ran on spot until Nov 13, 2026, when AWS kept taking it back mid-run |
| Nightly Airflow DAGs (platform skeleton and the Phase A signal run) | `pipelines/platform/dags`, `pipelines/signal/dags` | Live, every night at 10:00 UTC |
| Publish gate, write-audit-publish, status file, run metrics and incident records | `pipelines/platform/publish` | Live |
| Phase A steps: orbits (C1), Direct-to-Cell selector (C2), trails (C3), terrain horizon (C4), satellite windows (C5), FCC coverage (C6), dbt marts (C7), contract diff (C8), publish gate (C9), publisher (C10) | `pipelines/signal` | Live, in the nightly DAG |
| Trail API (C11) and trail page (C12) | `platform/serving/trails.py`, `app/src/pages/Trails.tsx` | Live. They read published files, so they work with the session box off |
| Phase B report API (C22): takes a hiker's "I had signal here" or "I had no signal here", with limits per visitor, per place and per day, and stores it in DynamoDB | `platform/serving/reports.py`, `platform/terraform/modules/serving/reports.tf` | Live |
| Phase B report buttons, part 1 (C21): the phone turns its location into a cell about 350 m across, so exact coordinates never leave it, and keeps a report until it can send it | `app/src/components/ReportButtons.tsx`, `app/src/lib/reports.ts`, `app/src/lib/cell.ts` | Live. A report waiting on the phone is sent when the page is open again |
| Phase B report buttons, part 2 (C21): on Android a small service worker sends a waiting report by itself when signal returns, even with the page closed. On iPhone the page sends it the next time it opens | `app/src/sw.ts`, `app/src/lib/backgroundSend.ts`, `app/src/lib/reportStore.ts` | Live. Tested on desktop Chrome and on an iPhone, not yet on an Android phone |
| Phase B nightly report copy, part 1 (C23): copies new reports into the lake, sets aside reports outside the mapped area or in a contradicting burst, and lets the copied ones expire after 30 days | `pipelines/signal/report_copy.py`, task `copy_reports` | Live, in the nightly DAG |
| Phase B report counts by area, part 2 (C23): counts each carrier's reports over the last 7 days per area (an H3 resolution 6 cell, about 36 km²) and shows them under the trail map. An area appears only once it has at least 5 reports, so a count cannot point at one hiker | `pipelines/signal/dbt/models/marts/fct_report_counts_area.sql`, `platform/serving/report_counts.py`, `app/src/components/ReportCounts.tsx` | Live. Until an area has 5 reports, the page says "Too few reports to show." |
| Phase B Ookla speed tests, part 1 (C13): once a quarter, loads Ookla's open mobile speed-test tiles for Arizona (about 11,200 tiles) with an H3 resolution 8 cell each, for the confidence model. Only a manifest of the worldwide file is kept | `pipelines/signal/ookla_tiles.py`, task `load_ookla` | Live, in the nightly DAG. 2026 Q3 is loaded (11,180 Arizona tiles) |
| Phase B every carrier, part 2 (C13): the coverage step loads the newest FCC file of each carrier and technology (AT&T, T-Mobile and Verizon, 4G LTE and 5G), and the trail map has a carrier picker that starts on the carrier the phone remembers | `pipelines/signal/signal_nightly.py`, `app/src/components/TrailSignalView.tsx` | Live. All six FCC files (release J26) are loaded. The map shows satellite reach only for T-Mobile, the carrier satellite texts need |
| Terraform: storage, Glue catalog, IAM, budget, alerts, audit trail, Parameter Store, registry, serving, session box, site, visitor data | `platform/terraform` | Applied to dev and live |
| Continuous integration, CodeQL and Dependabot | `.github/workflows` | Running on every pull request |
| Deploys | `.github/workflows/deploy.yml`, `terraform-apply.yml` | Each merge builds and scans the Airflow image, then deploys to dev and live after I approve each one |

Phase B has started. Not built yet:

- OpenCelliD tower locations (C13 part 3).
- The Snowflake warehouse (C15), and the labels and confidence model built from reports (C17).
- The orbit update stream, lineage, the trip assistant and operations hardening (C14, C16, C18 to C20, C24).

## Run the checks yourself

These steps assume Windows and PowerShell, with Python 3.11, Node 24 and Terraform 1.16 installed.

### 1. Python tests and lint

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
pytest
```

You should see `All checks passed!` from ruff. Pytest should report about 860 tests passing and about 25 skipped. The skipped ones need Airflow, Spark, Helm or Docker, which do not run on Windows here; CI runs them. The dbt tests run only if dbt has its own environment, because Airflow's packages refuse it: `py -3.11 -m venv .venv-dbt`, then `.\.venv-dbt\Scripts\python -m pip install --no-deps --only-binary :all: dbt-core==1.11.16 dbt-duckdb==1.11.1 duckdb==1.5.6` with the other packages in `platform/box/requirements-dbt.txt`.

### 2. Site

```powershell
cd app
npm ci
npm audit
npm run lint
npm run typecheck
npm test
npm run build
npm run dev
```

`npm test` should report about 257 tests passing. `npm run dev` starts a local preview. The status page reads `app/public/status.json`.

### 3. Terraform

```powershell
cd platform\terraform\modules\storage
terraform init -backend=false
terraform test
cd ..\..\..\..
terraform fmt -check -recursive platform\terraform
```

The module tests use a mock AWS provider and make no AWS calls. The IAM tests use the real provider with three lookups overridden, so they make no AWS calls either.

## How I work

- I write tests first. For each new behavior, I write a test, watch it fail, then write the code that passes it. The rules are in [CONTRIBUTING.md](CONTRIBUTING.md).
- Every timestamp is stored in UTC. The page converts it to the reader's local time.
- Every key lives in AWS Parameter Store. None is stored in this repository or in GitHub.
- The platform design, decision records and data contracts are in [docs/platform](docs/platform).
- The trip planner's own design, requirements, decision records and data contracts are in [docs/trip-planner](docs/trip-planner).

## License

I released the code under the MIT license ([LICENSE](LICENSE)). Each data source keeps its own license, and the project notes list them.

Includes data derived from Speedtest by Ookla® open data, licensed under CC BY-NC-SA 4.0. Derived data published here is shared under the same license.
