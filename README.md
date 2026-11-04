# Will I have signal out there?

I am building a trip planner for hikers, campers and backpackers. You pick a trail and see where each phone carrier has coverage, where it drops out, and when a Starlink Direct-to-Cell satellite text could get through. This repository holds the data platform behind the planner and the planner's code.

The site is live at **https://signal.johnwasikye.com**, with an "Under development" banner on every page. It shows no coverage or satellite times yet: I am building the Phase A data pipeline first, in build-plan order, and the trail page gets real data only once that data exists.

## What I have built

Everything runs on AWS in two separate environments, dev and live, built with Terraform and deployed by GitHub Actions.

| Part | Folder | Status |
|---|---|---|
| Serving API (FastAPI, DuckDB over Parquet, on Lambda behind API Gateway) | `platform/serving` | Live |
| Site (Vite, React, TypeScript, on CloudFront) | `app` | Live, with the development banner |
| Session box: a spot server that boots each night and runs Airflow and Spark on k3s, then stops | `platform/box` | Live. Saves the Airflow database to S3 before it stops |
| Nightly Airflow DAGs (platform skeleton and the Phase A signal run) | `pipelines/platform/dags`, `pipelines/signal/dags` | Live, every night at 10:00 UTC |
| Publish gate, write-audit-publish, status file, run metrics and incident records | `pipelines/platform/publish` | Live |
| Phase A steps: contract diff (C8), orbit ingest (C1), Direct-to-Cell selector (C2), trail loader (C3), terrain horizon (C4) | `pipelines/signal` | Built and running in the nightly DAG |
| Terraform: storage, Glue catalog, IAM, budget, alerts, audit trail, Parameter Store, registry, serving, session box, site, visitor data | `platform/terraform` | Applied to dev and live |
| Continuous integration, CodeQL and Dependabot | `.github/workflows` | Running on every pull request |
| Deploys | `.github/workflows/deploy.yml`, `terraform-apply.yml` | Each merge builds and scans the Airflow image, then deploys to dev and live after I approve each one |

Still to build for Phase A: satellite windows (C5), FCC coverage (C6), the dbt models (C7), the publish gate and publisher for trail data (C9, C10), the trail API (C11) and the trail page with real data (C12).

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

You should see `All checks passed!` from ruff. Pytest should report about 550 tests passing and about 20 skipped. The skipped ones need Airflow, Spark, Helm or Docker, which do not run on Windows here; CI runs them.

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

`npm run dev` starts a local preview. The status page reads `app/public/status.json`.

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
