# Will I have signal out there?

I am building a trip planner for hikers, campers and backpackers. You pick a trail and see where each phone carrier has coverage, where it drops out, and when a Starlink Direct-to-Cell satellite text could get through. This repository holds the data platform behind the planner and the planner's code.

The project is in its first phase. I am building the data platform first, and it is not deployed to AWS yet.

## What I have built

| Part | Folder | Status |
|---|---|---|
| Serving API (FastAPI, DuckDB over Parquet, Lambda handler) | `platform/serving` | Built and tested |
| Publish gate, write-audit-publish, status and run metrics | `pipelines/platform/publish` | Built and tested |
| Spark job that writes an Iceberg table | `pipelines/platform/spark/sample_iceberg_job.py` | Built, tested with a fake Spark session |
| Iceberg maintenance task | `pipelines/platform/spark/iceberg_maintenance.py` | Built, tested with a fake Spark session |
| Nightly Airflow DAG | `pipelines/platform/dags` | Built, not run yet (Airflow does not install on Windows) |
| Site template (React, TypeScript) | `app` | Built and tested |
| Terraform (storage, catalog, IAM, budget, parameters, visitor data) | `platform/terraform` | Built and validated. Storage and IAM have tests. Nothing applied to AWS |
| Continuous integration | `.github/workflows/ci.yml` | Written. Not run on GitHub yet |
| Dev container | `.devcontainer` | Written. Not opened in Codespaces yet |

I have not built these yet: the session box (the nightly server that runs Airflow and Spark), the AWS deployment, the Terraform state bucket, the live status page, and the trail data for Project 1.

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

You should see `All checks passed!` from ruff. Pytest should report the tests passing, with one test skipped because Airflow is not installed on Windows.

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
