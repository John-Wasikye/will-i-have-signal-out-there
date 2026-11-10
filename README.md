# Will I have signal out there?

I am building a trip planner for hikers, campers and backpackers. You pick a trail and see where each phone carrier has coverage, where it drops out, and when a Starlink Direct-to-Cell satellite text could get through. This repository holds the data platform behind the planner and the planner's code.

The site is live at **https://signal.johnwasikye.com**, with an "Under development" banner on every page. Phase A is deployed: for Bright Angel, South Kaibab and North Kaibab at Grand Canyon, the trail page shows where the FCC data says T-Mobile has coverage, and when a satellite is predicted to be reachable, for the next 24 hours. I have not checked these predictions in the field, so please do not rely on them for your safety.

## What I have built

Everything runs on AWS in two separate environments, dev and live, built with Terraform and deployed by GitHub Actions.

| Part | Folder | Status |
|---|---|---|
| Serving API (FastAPI, DuckDB over Parquet, on Lambda behind API Gateway) | `platform/serving` | Live |
| Site (Vite, React, TypeScript, on CloudFront) | `app` | Live, with the development banner |
| Session box: a spot server that boots each night and runs Airflow and Spark on k3s, then stops | `platform/box` | Live. Saves the Airflow database to S3 before it stops |
| Nightly Airflow DAGs (platform skeleton and the Phase A signal run) | `pipelines/platform/dags`, `pipelines/signal/dags` | Live, every night at 10:00 UTC |
| Publish gate, write-audit-publish, status file, run metrics and incident records | `pipelines/platform/publish` | Live |
| Phase A steps: orbits (C1), Direct-to-Cell selector (C2), trails (C3), terrain horizon (C4), satellite windows (C5), FCC coverage (C6), dbt marts (C7), contract diff (C8), publish gate (C9), publisher (C10) | `pipelines/signal` | Live, in the nightly DAG |
| Trail API (C11) and trail page (C12) | `platform/serving/trails.py`, `app/src/pages/Trails.tsx` | Live. They read published files, so they work with the session box off |
| Phase B report API (C22): takes a hiker's "I had signal here" or "I had no signal here", with limits per visitor, per place and per day, and stores it in DynamoDB | `platform/serving/reports.py`, `platform/terraform/modules/serving/reports.tf` | Live |
| Phase B report buttons, part 1 (C21): the phone turns its location into a cell about 350 m across, so exact coordinates never leave it, and keeps a report until it can send it | `app/src/components/ReportButtons.tsx`, `app/src/lib/reports.ts`, `app/src/lib/cell.ts` | Live. A report waiting on the phone is sent when the page is open again |
| Phase B nightly report copy, part 1 (C23): copies new reports into the lake, sets aside reports outside the mapped area or in a contradicting burst, and lets the copied ones expire after 30 days | `pipelines/signal/report_copy.py`, task `copy_reports` | Live, in the nightly DAG |
| Terraform: storage, Glue catalog, IAM, budget, alerts, audit trail, Parameter Store, registry, serving, session box, site, visitor data | `platform/terraform` | Applied to dev and live |
| Continuous integration, CodeQL and Dependabot | `.github/workflows` | Running on every pull request |
| Deploys | `.github/workflows/deploy.yml`, `terraform-apply.yml` | Each merge builds and scans the Airflow image, then deploys to dev and live after I approve each one |

Phase B has started. Not built yet:

- Sending a waiting report in the background on Android, without the page open (C21 part 2).
- Report counts by area, and showing them on the trail page (C23 part 2).
- Every carrier, Ookla speed tests and OpenCelliD (C13). The carrier list is AT&T, T-Mobile and Verizon until then.
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

You should see `All checks passed!` from ruff. Pytest should report about 800 tests passing and about 25 skipped. The skipped ones need Airflow, Spark, Helm or Docker, which do not run on Windows here; CI runs them. The dbt tests run only if dbt has its own environment, because Airflow's packages refuse it: `py -3.11 -m venv .venv-dbt`, then `.\.venv-dbt\Scripts\python -m pip install --no-deps --only-binary :all: dbt-core==1.11.16 dbt-duckdb==1.11.1 duckdb==1.5.6` with the other packages in `platform/box/requirements-dbt.txt`.

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

`npm test` should report about 220 tests passing. `npm run dev` starts a local preview. The status page reads `app/public/status.json`.

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
